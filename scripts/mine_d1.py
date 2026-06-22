"""D1 fundamental-ratio alpha miner for WorldQuant Brain.

Strategy (per user spec): mine SIMPLE, submittable, delay=1 alphas that
AVOID TOP3000. We lean on fundamental6 ratios (value/quality signals)
which empirically produce low-turnover, high-Sharpe, sector/subindustry
-neutralized alphas — the profile that passes WQ submit checks.

This does NOT reuse Alpha101 / the classical-factor library. The
expressions are original fundamental ratios.

Usage:
    python scripts/mine_d1.py            # run the default candidate batch
    python scripts/mine_d1.py --check ALPHA_ID   # run submit checks on an alpha
"""
from __future__ import annotations
import argparse, importlib.util, json, time, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

def _auth():
    spec = importlib.util.spec_from_file_location("cm", VENDOR/"core"/"credential_manager.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    cm = m.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("AUTH FAILED"); sys.exit(2)
    return cm.session

FIXED = {
    "instrumentType": "EQUITY", "region": "USA", "language": "FASTEXPR",
    "unitHandling": "VERIFY", "nanHandling": "OFF", "pasteurization": "ON",
    "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
}

def simulate(session, expr, settings, poll_timeout=420, poll_interval=6):
    body = {"type": "REGULAR", "settings": {**FIXED, **settings}, "regular": expr}
    for _ in range(6):
        r = session.post("https://api.worldquantbrain.com/simulations", json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 20)); continue
        break
    if r.status_code != 201:
        return {"ok": False, "expr": expr, "settings": settings,
                "err": f"submit-{r.status_code}:{r.text[:160]}"}
    loc = r.headers.get("Location")
    t0 = time.time()
    while time.time()-t0 < poll_timeout:
        time.sleep(poll_interval)
        rp = session.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(20); continue
        if rp.status_code != 200:
            continue
        d = rp.json(); st = d.get("status","")
        if st == "COMPLETE":
            aid = d.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
            a = ra.json(); isb = a.get("is") or {}
            checks = isb.get("checks") or []
            return {"ok": True, "expr": expr, "settings": settings, "alpha_id": aid,
                    "sharpe": isb.get("sharpe"), "turnover": isb.get("turnover"),
                    "fitness": isb.get("fitness"), "returns": isb.get("returns"),
                    "drawdown": isb.get("drawdown"), "margin": isb.get("margin"),
                    "longCount": isb.get("longCount"), "shortCount": isb.get("shortCount"),
                    "grade": a.get("grade"),
                    "checks": {c.get("name"): c.get("result") for c in checks},
                    "fail": [c.get("name") for c in checks if c.get("result")=="FAIL"]}
        if st in ("ERROR","FAILED","WARNING"):
            return {"ok": False, "expr": expr, "settings": settings,
                    "err": f"sim-{st}:{d.get('message','')[:200]}"}
    return {"ok": False, "expr": expr, "settings": settings, "err": "timeout"}

def run_batch(session, jobs, max_workers=3):
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(simulate, session, e, s): (e,s) for e,s in jobs}
        for fut in as_completed(futs):
            r = fut.result(); results.append(r)
            if r["ok"]:
                print(f"  [{ '✓' if not r['fail'] else 'x'}] SH={r['sharpe']:+.3f} "
                      f"TO={r['turnover']:.3f} FIT={r['fitness']:+.3f} grade={r['grade']:<9} "
                      f"fail={r['fail']} :: {r['expr'][:55]} | {r['settings'].get('universe')}/"
                      f"dec{r['settings'].get('decay')}/{r['settings'].get('neutralization')}")
            else:
                print(f"  [ERR] {r['err'][:90]} :: {r['expr'][:50]}")
    return results
