"""Round-1 QuantML factor port to WQ Brain.

Source: https://github.com/QuantMLResearch/QuantML  (`factor_zoo`).

The upstream is a Qlib-style minute-K factor zoo (1049 factors over
2016-2023 A-share, target = 5-day forward return). The structural
templates port cleanly to daily US bars; minute-aggregators
(`DownResample(..., 240, M)`) collapse to identity at daily frequency,
and `Med/Mad/Std` map to `ts_mean / manual MAD / ts_std_dev`.

Per the user's spec for this run:
- 5 structurally and logically distinct factors per round.
- Each factor has its OWN simulation settings (decay, truncation,
  neutralization, universe), tuned to the factor's character.

Each entry:
    id, category, idea, expression, settings_override
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
log = logging.getLogger("quantml-r1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
RESULTS = REPO / "WQ_QUANTML_RESULTS.json"

BASE_SETTINGS = {
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

FACTORS: list[dict] = [
    {
        "id": "QM_R1_01",
        "category": "amplitude",
        "idea": (
            "QuantML `DownResample(Max($high,N)/Min($low,N)-1, 240, M)` -- "
            "20-day true-range ratio. Wider range = higher realised vol, "
            "typically sells off; expect short-side premium."
        ),
        "original": "DownResample(Max($high,20)/Min($low,20)-1, 240, 'last')",
        "expression": "-1 * (ts_max(high, 20) / ts_min(low, 20) - 1)",
        "settings_override": {"decay": 4, "truncation": 0.08},
    },
    {
        "id": "QM_R1_02",
        "category": "median-bias",
        "idea": (
            "QuantML `DownResample(Med($close,240)/$close,240,'last')` -- "
            "60-day mean-to-current ratio. Mean reversion: when current "
            "is below mean, expect bounce (long); above, expect fade. "
            "Daily `ts_mean` substitutes for minute-bucket median."
        ),
        "original": "DownResample(Med($close,60)/$close, 240, 'last')",
        "expression": "ts_mean(close, 60) / close - 1",
        "settings_override": {
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R1_03",
        "category": "mad",
        "idea": (
            "QuantML `Mad($close, 240)/$close` -- normalised mean absolute "
            "deviation. High MAD = local instability; mean-reverts. "
            "Sign: negative (short instability)."
        ),
        "original": "Mad($close, 240)/$close",
        "expression": "-1 * ts_mean(abs(close - ts_mean(close, 20)), 20) / close",
        "settings_override": {"decay": 4, "truncation": 0.08},
    },
    {
        "id": "QM_R1_04",
        "category": "higher-moment",
        "idea": (
            "QuantML higher-moment: 60-day kurtosis of standardised "
            "returns. Fat-tailed names carry more crash risk. Short the "
            "tails. Market-neutral (`MARKET`) since kurtosis is a pure "
            "shape statistic with little industry-loading."
        ),
        "original": "Kurt(Ret($close, 1), 60)",
        "expression": "-1 * ts_mean(power(ts_zscore(returns, 60), 4), 60)",
        "settings_override": {
            "neutralization": "MARKET",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R1_05",
        "category": "liquidity",
        "idea": (
            "Amihud illiquidity ILLIQ_t = |r_t| / dollar_volume_t, smoothed "
            "20d. Illiquidity premium: long illiquid names. "
            "Use vwap*volume for dollar volume."
        ),
        "original": "Mean(Abs(Ret($close,1)) / ($total_turnover), 20)",
        "expression": "ts_mean(abs(returns) / (vwap * volume), 20)",
        "settings_override": {"decay": 4, "truncation": 0.08},
    },
]


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def submit_one(session, expression: str, settings: dict) -> dict:
    body = {"type": "REGULAR", "settings": settings, "regular": expression}
    log.info(f"-> POST /simulations  expr={expression[:80]!r}")
    log.info(f"   settings: decay={settings['decay']}  "
             f"neut={settings['neutralization']}  "
             f"trunc={settings['truncation']}  univ={settings['universe']}")
    r = session.post(
        "https://api.worldquantbrain.com/simulations", json=body, timeout=30
    )
    if r.status_code != 201:
        return {"ok": False, "stage": "submit", "status": r.status_code,
                "body": r.text[:500]}
    progress_url = r.headers.get("Location")
    if not progress_url:
        return {"ok": False, "stage": "submit", "error": "no Location header"}

    t0 = time.time()
    last_status = ""
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
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
                return {"ok": False, "stage": "complete-no-alpha-id",
                        "data": data}
            ra = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                timeout=30,
            )
            if ra.status_code != 200:
                return {"ok": False, "stage": "alpha-get",
                        "status": ra.status_code, "body": ra.text[:500],
                        "alpha_id": alpha_id}
            return {"ok": True, "alpha_id": alpha_id, "alpha": ra.json()}
        if status in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "simulation", "status": status,
                    "message": data.get("message", "")[:500], "data": data}
    return {"ok": False, "stage": "timeout"}


def main() -> int:
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    log.info(f"submitting {len(FACTORS)} QuantML round-1 factors")

    results: list[dict] = []
    for i, f in enumerate(FACTORS, 1):
        settings = {**BASE_SETTINGS, **f.get("settings_override", {})}
        log.info(f"=== [{i}/{len(FACTORS)}] {f['id']}  ({f['category']}) ===")
        res = submit_one(cm.session, f["expression"], settings)
        entry = {
            "id": f["id"],
            "category": f["category"],
            "idea": f["idea"],
            "original": f["original"],
            "expression": f["expression"],
            "settings": settings,
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
            log.info(f"   ERR stage={res.get('stage')} "
                     f"msg={(res.get('message') or res.get('body') or '')[:120]}")
        results.append(entry)
        RESULTS.write_text(json.dumps(results, indent=2))

    print()
    print("=" * 110)
    print(f"{'id':<11}{'cat':<15}{'SH':>7}{'TO':>7}{'FIT':>7}{'RET':>7}  alpha_id    expression")
    for r in results:
        def fmt(x):
            return f"{x:7.2f}" if isinstance(x, (int, float)) else "      -"
        if r.get("ok"):
            print(
                f"{r['id']:<11}{r['category']:<15}"
                f"{fmt(r.get('sharpe'))}{fmt(r.get('turnover'))}"
                f"{fmt(r.get('fitness'))}{fmt(r.get('returns'))}  "
                f"{r['alpha_id']:<11} {r['expression'][:55]}"
            )
        else:
            print(
                f"{r['id']:<11}{r['category']:<15}"
                f"{'-':>7}{'-':>7}{'-':>7}{'-':>7}  ERR         "
                f"{r['expression'][:55]} ({r.get('stage')})"
            )
    print("=" * 110)
    return 0


if __name__ == "__main__":
    sys.exit(main())
