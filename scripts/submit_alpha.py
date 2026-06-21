"""Submit alpha expressions to WorldQuant Brain `/simulations`.

Reads `MINING_REPORT.json` (or stdin), authenticates with credentials in
`credential.txt`, submits each `optimized` expression to the Brain
`/simulations` endpoint, polls until COMPLETE, then fetches the alpha's
IS metrics from `/alphas/{id}`.

Usage:
    python scripts/submit_alpha.py [MINING_REPORT.json]
    echo '{"factors":[{"optimized":"rank(close)","is_sharpe":...}]}' | \
        python scripts/submit_alpha.py -
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("submit")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# Default WQ Brain simulation settings -- aligned with the user's IS/OS spec
# (USA, TOP3000, delay=1, INDUSTRY-neutralized, 0.08 truncation).
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


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def submit_one(session, expression: str, settings: dict | None = None) -> dict:
    """Submit one expression. Returns dict with submission status, alpha_id,
    and either is_metrics (on success) or error.
    """
    s = dict(DEFAULT_SETTINGS)
    if settings:
        s.update(settings)
    body = {"type": "REGULAR", "settings": s, "regular": expression}

    log.info(f"-> POST /simulations  expr={expression[:80]!r}")
    r = session.post("https://api.worldquantbrain.com/simulations", json=body, timeout=30)
    if r.status_code != 201:
        return {"ok": False, "stage": "submit", "status": r.status_code,
                "body": r.text[:500], "expression": expression}
    progress_url = r.headers.get("Location")
    if not progress_url:
        return {"ok": False, "stage": "submit", "error": "no Location header",
                "expression": expression}
    log.info(f"   submitted, polling {progress_url}")

    # Poll
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
            log.warning(f"   progress poll {rp.status_code}: {rp.text[:200]}")
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
                        "data": data, "expression": expression}
            log.info(f"   COMPLETE alpha_id={alpha_id}; fetching metrics")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                              timeout=30)
            if ra.status_code != 200:
                return {"ok": False, "stage": "alpha-get",
                        "status": ra.status_code, "body": ra.text[:500],
                        "alpha_id": alpha_id, "expression": expression}
            return {"ok": True, "alpha_id": alpha_id,
                    "expression": expression, "alpha": ra.json()}
        if status in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "simulation",
                    "status": status,
                    "message": data.get("message", "")[:500],
                    "data": data, "expression": expression}

    return {"ok": False, "stage": "timeout", "expression": expression}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "MINING_REPORT.json"
    if src == "-":
        report = json.load(sys.stdin)
    else:
        report = json.load(open(src))
    factors = report["factors"] if "factors" in report else report

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2

    log.info(f"authenticated as {cm.credentials.username}")
    log.info(f"submitting {len(factors)} factors with settings={DEFAULT_SETTINGS}")

    results = []
    for i, f in enumerate(factors, 1):
        expr = f.get("optimized") or f.get("expression")
        if not expr:
            continue
        log.info(f"=== [{i}/{len(factors)}] ===")
        res = submit_one(cm.session, expr)
        # Carry over our local IS/OS metrics for side-by-side comparison
        for k in ("is_sharpe", "is_turnover", "is_annret",
                   "os_sharpe", "os_turnover", "os_annret"):
            if k in f:
                res[f"local_{k}"] = f[k]
        results.append(res)
        ok_marker = "OK " if res.get("ok") else "ERR"
        log.info(f"   [{ok_marker}] alpha_id={res.get('alpha_id', '-')}")

    out = REPO / "WQ_SUBMISSION_RESULTS.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"wrote {out}")

    # Stdout summary
    print()
    print("=" * 90)
    print(f"{'#':<3}{'ok':<4}{'WQ SH':>8}{'WQ TO':>8}{'WQ FIT':>8}{'WQ IR':>8}  alpha_id  expression")
    for i, r in enumerate(results, 1):
        if not r.get("ok"):
            print(f"{i:<3}ERR  {'-':>8}{'-':>8}{'-':>8}{'-':>8}  -         "
                  f"{r.get('expression','')[:70]}  ({r.get('stage','?')}: {r.get('message') or r.get('body','')[:60]})")
            continue
        a = r["alpha"]
        is_ = a.get("is", {}) or {}
        sh = is_.get("sharpe"); to = is_.get("turnover")
        fit = is_.get("fitness"); ir = is_.get("returns")  # 'returns' is annual
        def fmt(x): return f"{x:8.3f}" if isinstance(x, (int, float)) else "    -   "
        print(f"{i:<3}OK   {fmt(sh)}{fmt(to)}{fmt(fit)}{fmt(ir)}  {r['alpha_id']:<10}{r['expression'][:70]}")
    print("=" * 90)


if __name__ == "__main__":
    sys.exit(main() or 0)
