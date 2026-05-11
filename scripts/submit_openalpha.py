"""Submit translated OpenAlpha factors to WorldQuant Brain and filter
survivors by SH > 1.25, TO < 0.25, fitness > 1.

Reads `scripts/openalpha_factors.py`, authenticates via the standard
`credential.txt` flow, submits each expression to /simulations under
USA TOP3000, polls until complete, fetches /alphas/{id}, then writes:

  WQ_OPENALPHA_RESULTS.json   - every submission (ok or error)
  WQ_OPENALPHA_REPORT.json    - survivors only (SH>1.25, TO<0.25, FIT>1)

Usage:
    python scripts/submit_openalpha.py
    python scripts/submit_openalpha.py --start 0 --end 10   # subset
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("openalpha")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
SCRIPTS = REPO / "scripts"

sys.path.insert(0, str(SCRIPTS))
from openalpha_factors import all_expressions  # noqa: E402

# Authoritative WQ Brain submission settings -- aligned with CLAUDE.md spec
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
            log.warning(f"   progress {rp.status_code}: {rp.text[:200]}")
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    args = parser.parse_args()

    factors = all_expressions()
    factors = factors[args.start : args.end]
    log.info(f"loaded {len(factors)} OpenAlpha factors")

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed -- put credentials in credential.txt")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")
    log.info(f"settings: {DEFAULT_SETTINGS}")

    results: list[dict] = []
    survivors: list[dict] = []
    out_full = REPO / "WQ_OPENALPHA_RESULTS.json"
    out_surv = REPO / "WQ_OPENALPHA_REPORT.json"

    for i, f in enumerate(factors, 1):
        log.info(f"=== [{i}/{len(factors)}] {f['id']} {f['name']} ===")
        res = submit_one(cm.session, f["expression"])
        entry = {
            "id": f["id"],
            "name": f["name"],
            "original": f["original"],
            "expression": f["expression"],
            **res,
        }
        if res.get("ok"):
            is_ = (res["alpha"].get("is") or {})
            sh = is_.get("sharpe")
            to = is_.get("turnover")
            fit = is_.get("fitness")
            ret = is_.get("returns")
            entry["sharpe"] = sh
            entry["turnover"] = to
            entry["fitness"] = fit
            entry["returns"] = ret
            entry["drawdown"] = is_.get("drawdown")
            entry["margin"] = is_.get("margin")
            entry["checks"] = is_.get("checks")
            log.info(
                f"   OK alpha_id={res.get('alpha_id')} SH={sh} TO={to} FIT={fit}"
            )
            if (
                isinstance(sh, (int, float))
                and isinstance(to, (int, float))
                and isinstance(fit, (int, float))
                and sh > SH_THRESH
                and to < TO_THRESH
                and fit > FIT_THRESH
            ):
                survivors.append(entry)
                log.info("   *** SURVIVOR ***")
        else:
            log.info(
                f"   ERR stage={res.get('stage')} "
                f"msg={(res.get('message') or res.get('body') or '')[:120]}"
            )
        results.append(entry)
        # Persist incrementally so partial progress survives interrupts.
        out_full.write_text(json.dumps(results, indent=2))
        out_surv.write_text(json.dumps(survivors, indent=2))

    log.info(f"wrote {out_full} ({len(results)} entries)")
    log.info(f"wrote {out_surv} ({len(survivors)} survivors)")

    print()
    print("=" * 100)
    print(
        f"{'id':<6}{'ok':<5}{'WQ SH':>8}{'WQ TO':>8}{'WQ FIT':>8}{'WQ RET':>8}  alpha_id   expression"
    )
    for r in results:
        if not r.get("ok"):
            print(
                f"{r['id']:<6}ERR  "
                f"{'-':>8}{'-':>8}{'-':>8}{'-':>8}  -          "
                f"{r['expression'][:60]} ({r.get('stage')})"
            )
            continue

        def fmt(x):
            return f"{x:8.3f}" if isinstance(x, (int, float)) else "    -   "

        survived = (
            isinstance(r.get("sharpe"), (int, float))
            and r["sharpe"] > SH_THRESH
            and isinstance(r.get("turnover"), (int, float))
            and r["turnover"] < TO_THRESH
            and isinstance(r.get("fitness"), (int, float))
            and r["fitness"] > FIT_THRESH
        )
        marker = "**" if survived else "OK"
        print(
            f"{r['id']:<6}{marker:<5}{fmt(r.get('sharpe'))}{fmt(r.get('turnover'))}"
            f"{fmt(r.get('fitness'))}{fmt(r.get('returns'))}  "
            f"{r['alpha_id']:<10} {r['expression'][:60]}"
        )
    print("=" * 100)
    print(f"survivors (SH>{SH_THRESH}, TO<{TO_THRESH}, FIT>{FIT_THRESH}): "
          f"{len(survivors)} / {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
