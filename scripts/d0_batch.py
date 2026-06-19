"""Concurrent delay-0 IS simulation batch tester for WQ Brain.

Submits a list of (label, expression, settings) candidates concurrently,
polls each to COMPLETE, fetches /alphas/{id}, and prints IS metrics +
per-check pass/fail. Used to mine D0 factors that pass the submission
IS gate (LOW_SHARPE>1.25, LOW_FITNESS>1.0, turnover in [0.01,0.7],
sub-universe sharpe, etc.).

Usage:  python scripts/d0_batch.py
(edit CANDIDATES below, or import run_batch).
"""
from __future__ import annotations
import json, time, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

REPO = Path(__file__).resolve().parent.parent
API = "https://api.worldquantbrain.com"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 0, "decay": 0, "neutralization": "SUBINDUSTRY",
    "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY",
    "nanHandling": "OFF", "language": "FASTEXPR", "visualization": False,
    "maxTrade": "OFF", "testPeriod": "P0Y0M",
}


def auth():
    u, p = json.load(open(REPO / "credential.txt"))
    s = requests.Session(); s.auth = (u, p)
    r = s.post(f"{API}/authentication", timeout=30)
    r.raise_for_status()
    return s


def sim_one(s, expr, settings):
    st = dict(BASE); st.update(settings or {})
    body = {"type": "REGULAR", "settings": st, "regular": expr}
    for _ in range(40):
        r = s.post(f"{API}/simulations", json=body, timeout=30)
        if r.status_code == 429 or "CONCURRENT_SIMULATION_LIMIT" in r.text:
            time.sleep(float(r.headers.get("Retry-After") or 12)); continue
        break
    if r.status_code != 201:
        return {"ok": False, "stage": "submit", "code": r.status_code,
                "body": r.text[:300]}
    loc = r.headers.get("Location")
    t0 = time.time()
    while time.time() - t0 < 900:
        time.sleep(6)
        rp = s.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(20); continue
        if rp.status_code != 200:
            continue
        d = rp.json(); stt = d.get("status", "")
        if stt == "COMPLETE":
            aid = d.get("alpha")
            ra = s.get(f"{API}/alphas/{aid}", timeout=30)
            return {"ok": True, "alpha_id": aid, "alpha": ra.json()}
        if stt in ("ERROR", "FAILED"):
            return {"ok": False, "stage": "sim", "status": stt,
                    "msg": d.get("message", "")[:300]}
    return {"ok": False, "stage": "timeout"}


def run_batch(candidates, max_workers=3):
    s = auth()
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut = {ex.submit(sim_one, s, e, st): (lbl, e, st)
               for lbl, e, st in candidates}
        for f in as_completed(fut):
            lbl, e, st = fut[f]
            try:
                results[lbl] = (e, st, f.result())
            except Exception as ex2:
                results[lbl] = (e, st, {"ok": False, "stage": "exc",
                                        "msg": str(ex2)})
            _print_one(lbl, e, st, results[lbl][2])
    return results


def _print_one(lbl, e, st, r):
    if not r.get("ok"):
        print(f"[{lbl}] ERR {r.get('stage')}: {r.get('msg') or r.get('body','')[:120]}")
        return
    a = r["alpha"]; isb = a.get("is") or {}
    checks = isb.get("checks") or []
    fails = [c["name"] for c in checks if c.get("result") == "FAIL"]
    npass = sum(1 for c in checks if c.get("result") == "PASS")
    print(f"[{lbl}] SH={isb.get('sharpe'):+.2f} TO={isb.get('turnover'):.3f} "
          f"FIT={isb.get('fitness'):+.2f} RET={isb.get('returns'):+.3f} "
          f"DD={isb.get('drawdown'):.2f} checks={npass}/{len(checks)} "
          f"neut={st.get('neutralization','SUBIND')} id={r['alpha_id']} "
          f"FAILS={fails}")


if __name__ == "__main__":
    print("edit CANDIDATES / import run_batch", file=sys.stderr)
