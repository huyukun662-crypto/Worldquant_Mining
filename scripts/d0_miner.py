"""D0 factor miner for WorldQuant Brain.

Submits a batch of delay-0 candidate (expression, settings) pairs to
`/simulations` with bounded concurrency, fetches `/alphas/{id}` metrics,
then runs the pre-submission check `GET /alphas/{id}/check` on every
completed alpha. It never POSTs to the Submit-Alpha endpoint — per spec
we only *check* submittability.

D0 USA submit thresholds observed on this account (from /check):
    LOW_SHARPE  > 2.0      LOW_FITNESS > 1.3
    0.01 < turnover < 0.7  LOW_SUB_UNIVERSE_SHARPE (dynamic limit)

Usage:
    python scripts/d0_miner.py candidates.json [-o D0_MINING_REPORT.json]

candidates.json: [{"expression": "...", "settings": {"decay": 4, ...}}, ...]
Settings not given fall back to D0 defaults below.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import threading
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("d0-miner")

REPO = Path(__file__).resolve().parent.parent
API = "https://api.worldquantbrain.com"

D0_DEFAULTS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 0,
    "decay": 0,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

MAX_CONCURRENT = 3
POLL_TIMEOUT_S = 900


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def req(session, method, url, retries=6, **kw):
    kw.setdefault("timeout", 60)
    r = None
    for i in range(retries):
        try:
            r = session.request(method, url, **kw)
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(5 * (i + 1))
            continue
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 15)
            time.sleep(min(wait, 120))
            continue
        if r.status_code in (500, 502, 503, 504):
            time.sleep(5 * (i + 1))
            continue
        return r
    return r


def run_check(session, alpha_id: str, timeout_s: int = 600) -> dict:
    """Run pre-submission check; poll until checks are populated."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = req(session, "GET", f"{API}/alphas/{alpha_id}/check")
        if r is not None and r.status_code == 200 and r.text:
            d = r.json()
            checks = (d.get("is") or {}).get("checks") or []
            if checks:
                return d
        ra = (r.headers.get("Retry-After") if r is not None else None)
        time.sleep(float(ra) if ra else 10)
    return {"error": "check-timeout"}


def simulate_one(session, expression: str, settings: dict, sem, results, idx):
    full = dict(D0_DEFAULTS)
    full.update(settings or {})
    out = {"expression": expression, "settings": full, "ok": False}
    with sem:
        body = {"type": "REGULAR", "settings": full, "regular": expression}
        r = req(session, "POST", f"{API}/simulations", json=body)
        if r is None or r.status_code != 201:
            out["error"] = f"submit-{getattr(r, 'status_code', '?')}: " \
                           f"{getattr(r, 'text', '')[:300]}"
            results[idx] = out
            log.info(f"[{idx}] SUBMIT-ERR {out['error'][:120]}")
            return
        loc = r.headers.get("Location")
        t0 = time.time()
        while time.time() - t0 < POLL_TIMEOUT_S:
            time.sleep(8)
            rp = req(session, "GET", loc)
            if rp is None or rp.status_code != 200 or not rp.text:
                continue
            d = rp.json()
            st = d.get("status", "")
            if st == "COMPLETE":
                out["alpha_id"] = d.get("alpha")
                break
            if st in ("ERROR", "FAILED"):
                out["error"] = f"sim-{st}: {str(d.get('message', ''))[:300]}"
                results[idx] = out
                log.info(f"[{idx}] SIM-{st} {expression[:60]}")
                return
            # WARNING status still produces an alpha
            if st == "WARNING":
                out["alpha_id"] = d.get("alpha")
                out["warning"] = str(d.get("message", ""))[:300]
                break
        if not out.get("alpha_id"):
            out["error"] = "poll-timeout"
            results[idx] = out
            return

    # Outside the semaphore: fetch metrics + run check
    aid = out["alpha_id"]
    ra = req(session, "GET", f"{API}/alphas/{aid}")
    if ra is not None and ra.status_code == 200:
        ay = ra.json()
        isb = ay.get("is") or {}
        out.update(
            ok=True,
            sharpe=isb.get("sharpe"),
            turnover=isb.get("turnover"),
            fitness=isb.get("fitness"),
            returns=isb.get("returns"),
            drawdown=isb.get("drawdown"),
            margin=isb.get("margin"),
            longCount=isb.get("longCount"),
            shortCount=isb.get("shortCount"),
        )
    chk = run_check(session, aid)
    checks = (chk.get("is") or {}).get("checks") or []
    out["checks"] = checks
    out["checks_failed"] = [c["name"] for c in checks if c.get("result") == "FAIL"]
    out["submittable"] = bool(checks) and not out["checks_failed"] and \
        all(c.get("result") in ("PASS", "PENDING") for c in checks)
    results[idx] = out
    log.info(f"[{idx}] SH={out.get('sharpe')} TO={out.get('turnover')} "
             f"FIT={out.get('fitness')} fail={out['checks_failed']} "
             f"id={aid} {expression[:70]}")


def run_batch(session, candidates: list[dict]) -> list[dict]:
    sem = threading.Semaphore(MAX_CONCURRENT)
    results: list = [None] * len(candidates)
    threads = []
    for i, c in enumerate(candidates):
        t = threading.Thread(target=simulate_one, args=(
            session, c["expression"], c.get("settings") or {}, sem, results, i))
        t.start()
        threads.append(t)
        time.sleep(2)  # stagger POSTs
    for t in threads:
        t.join()
    return [r for r in results if r]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", help="JSON file with candidate list")
    ap.add_argument("-o", "--out", default="D0_MINING_REPORT.json")
    args = ap.parse_args()

    cands = json.load(open(args.candidates))
    cm_mod = _load(REPO / "vendor" / "worldquant-miner" / "core" /
                   "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed")
        return 2
    log.info(f"authenticated as {cm.credentials.username}; "
             f"{len(cands)} candidates, concurrency {MAX_CONCURRENT}")

    results = run_batch(cm.session, cands)

    out_path = Path(args.out)
    existing = []
    if out_path.exists():
        try:
            existing = json.load(open(out_path))
        except Exception:
            existing = []
    existing.extend(results)
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

    print()
    print("=" * 100)
    print(f"{'SH':>6}{'TO':>7}{'FIT':>6}  {'submittable':<12}{'failed':<38}expression")
    for r in sorted(results, key=lambda x: -(x.get("sharpe") or -99)):
        if not r.get("ok"):
            print(f"  ERR  {str(r.get('error'))[:90]}")
            continue
        print(f"{r['sharpe']:6.2f}{r['turnover']:7.3f}{r['fitness']:6.2f}  "
              f"{str(r['submittable']):<12}{','.join(r['checks_failed'])[:36]:<38}"
              f"{r['expression'][:60]}")
    print("=" * 100)
    n_sub = sum(1 for r in results if r.get("submittable"))
    print(f"submittable candidates: {n_sub}/{len(results)}  -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
