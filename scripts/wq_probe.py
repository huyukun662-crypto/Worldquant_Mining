"""Quick probe: authenticate + test delay=0 availability on WQ Brain.

Submits one trivial reversal expression at delay=0 and reports whether the
account tier accepts delay-0 simulations (historically returned HTTP 400
"Delay 0 is not available" on this account; user now wants D0 factors, so
we verify empirically).
"""
from __future__ import annotations
import importlib.util, json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def auth():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("AUTH FAILED"); sys.exit(2)
    print("authenticated as", cm.credentials.username)
    return cm.session


def probe(session, expr, delay, universe="TOP3000", neut="SUBINDUSTRY",
          decay=4, trunc=0.08):
    settings = {
        "instrumentType": "EQUITY", "region": "USA", "universe": universe,
        "delay": delay, "decay": decay, "neutralization": neut,
        "truncation": trunc, "pasteurization": "ON", "unitHandling": "VERIFY",
        "nanHandling": "OFF", "language": "FASTEXPR", "visualization": False,
        "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }
    body = {"type": "REGULAR", "settings": settings, "regular": expr}
    r = session.post("https://api.worldquantbrain.com/simulations", json=body, timeout=30)
    print(f"POST delay={delay} status={r.status_code} body={r.text[:200]}")
    if r.status_code != 201:
        return {"ok": False, "status": r.status_code, "body": r.text[:300]}
    loc = r.headers.get("Location")
    t0 = time.time()
    while time.time() - t0 < 600:
        time.sleep(5)
        rp = session.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(20); continue
        if rp.status_code != 200:
            continue
        data = rp.json(); st = data.get("status", "")
        if st == "COMPLETE":
            aid = data.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
            ay = ra.json(); isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            print(f"COMPLETE alpha={aid} SH={isb.get('sharpe')} TO={isb.get('turnover')} "
                  f"FIT={isb.get('fitness')} RET={isb.get('returns')} DD={isb.get('drawdown')}")
            for c in checks:
                print("   check", c.get("name"), c.get("result"),
                      c.get("value"), c.get("limit"))
            return {"ok": True, "alpha_id": aid, "is": isb}
        if st in ("ERROR", "FAILED", "WARNING"):
            print("SIM", st, data.get("message", "")[:300])
            return {"ok": False, "status": st, "message": data.get("message", "")}
    print("poll timeout")
    return {"ok": False, "status": "timeout"}


if __name__ == "__main__":
    s = auth()
    expr = sys.argv[1] if len(sys.argv) > 1 else "-ts_delta(close, 1)"
    delay = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    probe(s, expr, delay)
