"""D0 (delay=0) factor miner + submission checker for WorldQuant Brain.

Per the user spec (2026-06 session, account YW92315):
  * ONLY delay=0 factors.
  * Must pass the WQ Brain *submission* check (GET /alphas/{id}/check),
    not merely the IS gates. D0 submission limits observed:
        LOW_SHARPE   >= 2.0     (vs 1.25 for delay=1)
        LOW_FITNESS  >= 1.3     (vs 1.0  for delay=1)
        0.01 < turnover < 0.7
        LOW_SUB_UNIVERSE_SHARPE > 0.01
        CONCENTRATED_WEIGHT PASS
        SELF_CORRELATION   PASS  (resolves once IS gates pass)
  * Concise expressions, regularization functions (winsorize/zscore/
    normalize/scale/ts_zscore/group_zscore), economic meaning, niche
    operators (ts_av_diff, ts_arg_max/min, days_from_last_change, hump,
    ts_scale, ts_quantile, signed_power, last_diff_value, ts_regression).
  * No implied-volatility (IV) / options fields -- price-volume only.
  * No Alpha101 / classical-template reuse.

This module is self-contained: authenticate, submit a batch of
(expression, settings) candidates with bounded concurrency, poll each to
COMPLETE, collect IS metrics + checks, and for IS-gate survivors run the
submission check.

Usage:
    python scripts/d0_mine.py            # run the built-in candidate batch
    python scripts/d0_mine.py --check ALPHA_ID   # re-run submission check
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("d0")

REPO = Path(__file__).resolve().parent.parent
API = "https://api.worldquantbrain.com"

# D0 submission limits (the canonical bar for this account/competition)
D0_SHARPE_FLOOR = 2.0
D0_FITNESS_FLOOR = 1.3
TURNOVER_LO, TURNOVER_HI = 0.01, 0.7

FIXED = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "delay": 0,                 # D0 ONLY
    "language": "FASTEXPR",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "pasteurization": "ON",
    "visualization": False,
}


def authenticate() -> requests.Session:
    u, p = json.load(open(REPO / "credential.txt"))
    s = requests.Session()
    s.auth = HTTPBasicAuth(u, p)
    r = s.post(f"{API}/authentication", timeout=20)
    r.raise_for_status()
    log.info(f"authenticated as {u} -> {r.json().get('user', {}).get('id')}")
    return s


def _full_settings(settings: dict) -> dict:
    s = dict(FIXED)
    s.update(settings)
    return s


def submit_sim(session, expression: str, settings: dict,
               poll_timeout_s: int = 600) -> dict:
    """Submit one simulation, poll to COMPLETE, fetch IS metrics+checks."""
    body = {"type": "REGULAR", "settings": _full_settings(settings),
            "regular": expression}
    # POST with 429/auth retry
    for attempt in range(6):
        r = session.post(f"{API}/simulations", json=body, timeout=30)
        if r.status_code == 401:
            session.post(f"{API}/authentication", timeout=20)
            continue
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 15)); continue
        break
    if r.status_code != 201:
        return {"ok": False, "expression": expression, "settings": settings,
                "error": f"submit-{r.status_code}: {r.text[:200]}"}
    loc = r.headers.get("Location")
    if not loc:
        return {"ok": False, "expression": expression, "settings": settings,
                "error": "no Location"}

    t0 = time.time()
    while time.time() - t0 < poll_timeout_s:
        rp = session.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(float(rp.headers.get("Retry-After") or 10)); continue
        if rp.status_code != 200:
            time.sleep(5); continue
        d = rp.json()
        st = d.get("status")
        if st == "COMPLETE":
            aid = d.get("alpha")
            ra = session.get(f"{API}/alphas/{aid}", timeout=30)
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = {c["name"]: c for c in (isb.get("checks") or [])}
            return {"ok": True, "expression": expression, "settings": settings,
                    "alpha_id": aid,
                    "sharpe": isb.get("sharpe"), "fitness": isb.get("fitness"),
                    "turnover": isb.get("turnover"), "returns": isb.get("returns"),
                    "drawdown": isb.get("drawdown"), "margin": isb.get("margin"),
                    "longCount": isb.get("longCount"),
                    "shortCount": isb.get("shortCount"),
                    "subuniv": (checks.get("LOW_SUB_UNIVERSE_SHARPE") or {}).get("value"),
                    "checks": isb.get("checks")}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "expression": expression, "settings": settings,
                    "error": f"sim-{st}: {str(d.get('message',''))[:200]}"}
        time.sleep(float(rp.headers.get("Retry-After") or 5))
    return {"ok": False, "expression": expression, "settings": settings,
            "error": "poll-timeout"}


def check_submission(session, alpha_id: str) -> dict:
    """GET /alphas/{id}/check -- the submittability check (incl. self-corr)."""
    for _ in range(40):
        r = session.get(f"{API}/alphas/{alpha_id}/check", timeout=60)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 10)); continue
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code, "body": r.text[:300]}
        d = r.json()
        checks = ((d.get("is") or {}).get("checks")) or []
        pending = [c for c in checks if c.get("result") == "PENDING"]
        if pending:
            time.sleep(float(r.headers.get("Retry-After") or 5)); continue
        return {"ok": True, "checks": checks}
    return {"ok": False, "error": "check-timeout-pending"}


def run_batch(session, candidates: list[dict], max_workers: int = 3,
              out_path: Path | None = None) -> list[dict]:
    """candidates: [{expr, settings}]. Returns list of result dicts.
    Writes partial results to out_path after EACH completion so a timeout
    or crash never loses data."""
    results = []
    lock = threading.Lock()

    def work(c):
        log.info(f"-> SUBMIT d0 {c['settings'].get('neutralization','?'):<11} "
                 f"dec={c['settings'].get('decay'):<3} {c['expr'][:70]}")
        res = submit_sim(session, c["expr"], c["settings"])
        with lock:
            if res.get("ok"):
                log.info(f"   [OK ] SH={res['sharpe']:+.3f} FIT={res['fitness']:+.3f} "
                         f"TO={res['turnover']:.3f} subU={res['subuniv']} "
                         f"{res['alpha_id']}  {c['expr'][:55]}")
            else:
                log.info(f"   [ERR] {res['error'][:90]}  {c['expr'][:50]}")
            results.append(res)
            if out_path is not None:
                with open(out_path, "w") as f:
                    json.dump(results, f, indent=2)
        return res

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(work, c) for c in candidates]
        for f in as_completed(futs):
            f.result()
    return results


def print_table(results: list[dict]):
    ok = [r for r in results if r.get("ok")]
    ok.sort(key=lambda r: (r.get("sharpe") or -99), reverse=True)
    print("\n" + "=" * 118)
    print(f"{'SH':>7}{'FIT':>7}{'TO':>7}{'subU':>7}  {'alpha_id':<10} "
          f"{'neut':<12}{'univ':<9}{'dec':>4}  expression")
    for r in ok:
        s = r["settings"]
        print(f"{(r['sharpe'] or 0):7.3f}{(r['fitness'] or 0):7.3f}"
              f"{(r['turnover'] or 0):7.3f}{(r['subuniv'] or 0):7.3f}  "
              f"{r['alpha_id']:<10} {s.get('neutralization',''):<12}"
              f"{s.get('universe',''):<9}{s.get('decay',0):>4}  {r['expression'][:60]}")
    print("=" * 118)
    # D0 submission-ready survivors (IS gates)
    surv = [r for r in ok
            if (r.get("sharpe") or 0) >= D0_SHARPE_FLOOR
            and (r.get("fitness") or 0) >= D0_FITNESS_FLOOR
            and TURNOVER_LO < (r.get("turnover") or 0) < TURNOVER_HI
            and (r.get("subuniv") or -1) > 0.01]
    print(f"IS-gate survivors (SH>={D0_SHARPE_FLOOR}, FIT>={D0_FITNESS_FLOOR}, "
          f"{TURNOVER_LO}<TO<{TURNOVER_HI}, subU>0.01): {len(surv)}")
    for r in surv:
        print(f"   {r['alpha_id']}  {r['expression']}")
    return surv


# ----------------------------------------------------------------------------
# Built-in candidate batch: economic-meaning D0 factors, niche operators,
# regularization wrappers, price-volume only (no IV).
# ----------------------------------------------------------------------------
def default_candidates() -> list[dict]:
    base = {"universe": "TOP3000", "decay": 4, "truncation": 0.08,
            "neutralization": "SUBINDUSTRY"}

    def s(**kw):
        d = dict(base); d.update(kw); return d

    exprs = [
        # --- Short-term reversal (overreaction) via niche ts_av_diff ---
        # ts_av_diff(x,d) = x - ts_mean(x,d): deviation from own MA -> revert.
        "-zscore(ts_av_diff(vwap, 5))",
        "-winsorize(zscore(ts_av_diff(returns, 5)), std=4)",
        # --- Close-location reversal (closed near high -> overbought) ---
        "-rank(divide(subtract(close, low), subtract(high, low)))",
        # --- Volume-shock reversal (niche ts_av_diff on volume) ---
        "-normalize(ts_av_diff(volume, 20))",
        # --- Recency-of-extreme momentum (niche ts_arg_min) ---
        "rank(ts_arg_max(close, 20))",
        # --- Amihud illiquidity premium (regularized) ---
        "winsorize(zscore(divide(abs(returns), volume)), std=4)",
    ]
    return [{"expr": e, "settings": s()} for e in exprs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", type=str, default=None,
                    help="Run submission check on an existing alpha_id and exit")
    ap.add_argument("--candidates", type=str, default=None,
                    help="JSON file: [{expr, settings}] to run instead of built-in")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", type=str, default="D0_MINING_REPORT.json")
    args = ap.parse_args()

    session = authenticate()

    if args.check:
        res = check_submission(session, args.check)
        print(json.dumps(res, indent=2))
        return 0

    if args.candidates:
        cands = json.load(open(args.candidates))
    else:
        cands = default_candidates()
    log.info(f"running {len(cands)} D0 candidates, {args.workers} concurrent")
    out_path = REPO / args.out
    results = run_batch(session, cands, max_workers=args.workers,
                        out_path=out_path)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    surv = print_table(results)

    # Auto-run submission check on the best IS survivor
    if surv:
        best = max(surv, key=lambda r: r["sharpe"])
        log.info(f"submission-checking best survivor {best['alpha_id']}")
        chk = check_submission(session, best["alpha_id"])
        print(json.dumps(chk, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
