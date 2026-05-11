"""Round-2: resubmit the 9 OpenAlpha factors that errored in round 1.

Errors fell into three classes; fixes applied per class:

1. inaccessible operator `ts_returns`
   -> manual expansion `(x / ts_delay(x, 1) - 1)`.
   Affected: OA04.

2. inaccessible operators `ts_skewness`, `ts_kurtosis`
   -> manual moment formulas using `power` (which is accessible):
        skew(x,d) = ts_mean(power(x - ts_mean(x,d), 3), d)
                    / power(ts_std_dev(x,d), 3)
        kurt(x,d) = ts_mean(power(x - ts_mean(x,d), 4), d)
                    / power(ts_std_dev(x,d), 4) - 3
   Affected: OA21, OA22, OA23, OA34, OA35.

3. unit incompatibility passing `volume` (Unit[TSShare]) or
   `vwap*volume` (Unit[TSPrice,TSShare]) into `ts_regression` 2nd arg
   (expects unit-free or Unit[TSPrice])
   -> wrap the offending arg in `rank(...)` to strip units.
   Affected: OA05, OA16, OA28.

Reads any *previous* WQ_OPENALPHA_RESULTS.json (round-1 plus older
checkpoints), updates the erroring entries in place with the new
re-submitted result, and re-derives WQ_OPENALPHA_REPORT.json
(survivors only: SH>1.25 AND TO<0.25 AND fitness>1).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("openalpha-fix")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
RESULTS = REPO / "WQ_OPENALPHA_RESULTS.json"
REPORT = REPO / "WQ_OPENALPHA_REPORT.json"

DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 0,
    "neutralization": "INDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 5

SH_THRESH = 1.25
TO_THRESH = 0.25
FIT_THRESH = 1.0


# (id, name, new FASTEXPR after fixes)
FIXES: list[tuple[str, str, str]] = [
    (
        "OA04",
        "corr_lowret_ret_3",
        "ts_corr(low / ts_delay(low, 1) - 1, returns, 3)",
    ),
    (
        "OA05",
        "ols_residual_openClose_volume_10",
        # wrap delayed volume in rank() to strip TSShare units
        "ts_regression(open / ts_delay(close, 1), rank(ts_delay(volume, 1)), 10, rettype=0)",
    ),
    (
        "OA16",
        "neg_ols_beta_ret_volume_10",
        "-1 * ts_regression(returns, rank(volume), 10, rettype=2)",
    ),
    (
        "OA21",
        "neg_skew_close_20",
        "-1 * ts_mean(power(close - ts_mean(close, 20), 3), 20) "
        "/ power(ts_std_dev(close, 20), 3)",
    ),
    (
        "OA22",
        "skew_vwap_minus_close_10",
        "ts_mean(power((vwap - close) - ts_mean(vwap - close, 10), 3), 10) "
        "/ power(ts_std_dev(vwap - close, 10), 3)",
    ),
    (
        "OA23",
        "kurt_delta_close_20",
        "ts_mean(power(ts_delta(close, 1) - ts_mean(ts_delta(close, 1), 20), 4), 20) "
        "/ power(ts_std_dev(ts_delta(close, 1), 20), 4) - 3",
    ),
    (
        "OA28",
        "neg_regression_marketRet_amount_30",
        "-1 * ts_regression(group_mean(returns, 1, market), "
        "rank(vwap * volume), 30, rettype=0)",
    ),
    (
        "OA34",
        "ols_beta_skewRet_ret_5",
        # skew(returns, 5) manual
        "ts_regression("
        "ts_mean(power(returns - ts_mean(returns, 5), 3), 5) "
        "/ power(ts_std_dev(returns, 5), 3), "
        "returns, 5, rettype=2)",
    ),
    (
        "OA35",
        "neg_regression_skewRet_ret_7",
        "-1 * ts_regression("
        "ts_mean(power(returns - ts_mean(returns, 3), 3), 3) "
        "/ power(ts_std_dev(returns, 3), 3), "
        "returns, 7, rettype=0)",
    ),
]


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def submit_one(session, expression: str) -> dict:
    body = {
        "type": "REGULAR",
        "settings": DEFAULT_SETTINGS,
        "regular": expression,
    }
    log.info(f"-> POST /simulations  expr={expression[:80]!r}")
    r = session.post(
        "https://api.worldquantbrain.com/simulations", json=body, timeout=30
    )
    if r.status_code != 201:
        return {
            "ok": False,
            "stage": "submit",
            "status": r.status_code,
            "body": r.text[:500],
        }
    progress_url = r.headers.get("Location")
    if not progress_url:
        return {"ok": False, "stage": "submit", "error": "no Location header"}

    t0 = time.time()
    last_status = ""
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            log.info("   429 throttled; sleeping 30s")
            time.sleep(30)
            continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        status = data.get("status", "")
        if status != last_status:
            log.info(f"   status={status} ({int(time.time() - t0)}s)")
            last_status = status
        if status == "COMPLETE":
            alpha_id = data.get("alpha")
            if not alpha_id:
                return {
                    "ok": False,
                    "stage": "complete-no-alpha-id",
                    "data": data,
                }
            ra = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                timeout=30,
            )
            if ra.status_code != 200:
                return {
                    "ok": False,
                    "stage": "alpha-get",
                    "status": ra.status_code,
                    "body": ra.text[:500],
                    "alpha_id": alpha_id,
                }
            return {"ok": True, "alpha_id": alpha_id, "alpha": ra.json()}
        if status in ("ERROR", "FAILED", "WARNING"):
            return {
                "ok": False,
                "stage": "simulation",
                "status": status,
                "message": data.get("message", "")[:500],
                "data": data,
            }
    return {"ok": False, "stage": "timeout"}


def main() -> int:
    results = json.loads(RESULTS.read_text()) if RESULTS.exists() else []
    by_id = {r["id"]: r for r in results}

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")
    log.info(f"resubmitting {len(FIXES)} fixes")

    for i, (fid, name, new_expr) in enumerate(FIXES, 1):
        log.info(f"=== [{i}/{len(FIXES)}] {fid} {name} ===")
        res = submit_one(cm.session, new_expr)
        entry: dict = {
            "id": fid,
            "name": name,
            "original": by_id.get(fid, {}).get("original", ""),
            "expression": new_expr,
            **res,
        }
        if res.get("ok"):
            is_ = res["alpha"].get("is") or {}
            entry["sharpe"] = is_.get("sharpe")
            entry["turnover"] = is_.get("turnover")
            entry["fitness"] = is_.get("fitness")
            entry["returns"] = is_.get("returns")
            entry["drawdown"] = is_.get("drawdown")
            entry["margin"] = is_.get("margin")
            entry["checks"] = is_.get("checks")
            log.info(
                f"   OK alpha_id={res.get('alpha_id')} "
                f"SH={entry['sharpe']} TO={entry['turnover']} "
                f"FIT={entry['fitness']}"
            )
        else:
            log.info(
                f"   ERR stage={res.get('stage')} "
                f"msg={(res.get('message') or res.get('body') or '')[:120]}"
            )
        by_id[fid] = entry
        # Persist after each
        merged = list(by_id.values())
        RESULTS.write_text(json.dumps(merged, indent=2))

        survivors = [
            r for r in merged
            if r.get("ok")
            and isinstance(r.get("sharpe"), (int, float))
            and r["sharpe"] > SH_THRESH
            and isinstance(r.get("turnover"), (int, float))
            and r["turnover"] < TO_THRESH
            and isinstance(r.get("fitness"), (int, float))
            and r["fitness"] > FIT_THRESH
        ]
        REPORT.write_text(json.dumps(survivors, indent=2))

    log.info(f"final: {len(by_id)} entries, "
             f"{sum(1 for x in by_id.values() if x.get('ok'))} ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
