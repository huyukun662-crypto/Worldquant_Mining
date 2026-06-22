"""Submit D=0 candidates to /simulations and report whether they would pass
WQ Brain's `is.checks` (i.e. would survive `Submit Alpha`). Does NOT call
the Submit Alpha endpoint -- only checks the IS metrics + checks block.

Usage: python scripts/check_d0_candidates.py
"""

from __future__ import annotations
import importlib.util, json, sys, time, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

D0_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 0, "decay": 0, "neutralization": "INDUSTRY",
    "truncation": 0.08, "pasteurization": "ON",
    "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False,
    "maxTrade": "OFF", "testPeriod": "P0Y0M",
}

POLL_TIMEOUT_S = 900
POLL_INTERVAL_S = 8


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def submit(session, item, lock):
    expr, overrides = (item, {}) if isinstance(item, str) else item
    s = dict(D0_SETTINGS); s.update(overrides)
    body = {"type": "REGULAR", "settings": s, "regular": expr}
    with lock:
        r = session.post("https://api.worldquantbrain.com/simulations", json=body, timeout=30)
    if r.status_code != 201:
        return {"ok": False, "stage": "submit", "status": r.status_code,
                "body": r.text[:300], "expression": expr, "settings": overrides}
    loc = r.headers.get("Location")
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        d = rp.json()
        st = d.get("status", "")
        if st == "COMPLETE":
            aid = d.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
            return {"ok": True, "alpha_id": aid, "expression": expr,
                    "alpha": ra.json() if ra.status_code == 200 else {}}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "sim", "status": st,
                    "message": d.get("message", "")[:300], "expression": expr, "settings": overrides}
    return {"ok": False, "stage": "timeout", "expression": expr, "settings": overrides}


def summarize(r):
    if not r.get("ok"):
        return f"  ERR  {r.get('stage')}: {r.get('message') or r.get('body','')[:120]}  | {r.get('expression','')}"
    a = r["alpha"]; is_ = a.get("is", {}) or {}
    sh = is_.get("sharpe"); to = is_.get("turnover")
    fit = is_.get("fitness"); ret = is_.get("returns"); dd = is_.get("drawdown")
    checks = is_.get("checks", []) or []
    fails = [c["name"] for c in checks if c.get("result") == "FAIL"]
    pends = [c["name"] for c in checks if c.get("result") == "PENDING"]
    passes_submit = len(fails) == 0
    tag = "PASS-ALL" if passes_submit else "FAIL"
    return (f"  {tag:9s} SH={sh}  TO={to}  FIT={fit}  RET={ret}  DD={dd}\n"
            f"            id={r['alpha_id']}  fails={fails} pending={pends}\n"
            f"            expr={r['expression']}")


BEST_PV = ("ts_decay_linear(-rank(ts_av_diff(vwap, 10)) + -rank(ts_corr(vwap, volume, 22)) "
           "+ -rank(ts_corr(vwap, volume, 5)), 5)")

SUB = {"neutralization": "SUBINDUSTRY"}
QUAD = ("ts_decay_linear(-rank(ts_av_diff(vwap, 10)) + -rank(ts_corr(vwap, volume, 22)) "
        "+ -rank(ts_corr(vwap, volume, 5)) + -rank(ts_corr(vwap, volume, 44)), 5)")
WIN_DECAY10 = ("ts_decay_linear(-rank(ts_av_diff(vwap, 10)) + -rank(ts_corr(vwap, volume, 22)) "
               "+ -rank(ts_corr(vwap, volume, 5)), 10)")

CANDIDATES = [
    # Longer decay under SUB
    (WIN_DECAY10, SUB),
    # Quad-horizon stack under SUB
    (QUAD, SUB),
    # SUB + tighter truncation 0.05
    (BEST_PV, {"neutralization": "SUBINDUSTRY", "truncation": 0.05}),
    # SUB + decay=10 + winsorize wrapper
    (f"winsorize({WIN_DECAY10}, std=3)", SUB),
    # Two-leg pure mean-rev + corr10, longer corr 60
    ("ts_decay_linear(-rank(ts_av_diff(vwap, 10)) + -rank(ts_corr(vwap, volume, 22)) + -rank(ts_corr(vwap, volume, 60)), 5)", SUB),
    # Smoothed pre-rank under SUB (smaller TO -> higher FIT)
    ("ts_decay_linear(-rank(ts_mean(ts_av_diff(vwap, 10), 3)) + -rank(ts_corr(vwap, volume, 22)) + -rank(ts_corr(vwap, volume, 5)), 5)", SUB),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    assert cm.authenticate(auto_load=True, auto_prompt=False), "auth fail"
    print(f"authenticated as {cm.credentials.username}\n")
    print(f"submitting {len(CANDIDATES)} D=0 candidates (concurrency=2)\n")
    lock = threading.Lock()
    results = []
    # Concurrency=2 per account tier
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(submit, cm.session, c, lock): c for c in CANDIDATES}
        for f in as_completed(futs):
            r = f.result(); results.append(r)
            print(summarize(r)); print()
    out = REPO / "WQ_D0_CHECK.json"
    json.dump(results, open(out, "w"), indent=2)
    print(f"\nwrote {out}")
    passers = [r for r in results if r.get("ok") and not [c for c in (r["alpha"].get("is",{}).get("checks",[]) or []) if c.get("result")=="FAIL"]]
    print(f"\n{len(passers)}/{len(results)} candidates pass all is.checks (would pass Submit)")
    for r in passers:
        is_ = r["alpha"]["is"]
        print(f"  -> SH={is_.get('sharpe')} TO={is_.get('turnover')} FIT={is_.get('fitness')}  {r['expression']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
