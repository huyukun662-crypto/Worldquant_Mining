"""D0 (delay=0) factor mining + submit-readiness check for WQ Brain.

Per the user spec for this task:
  - delay=0 only
  - simple expressions
  - include regularization functions (winsorize/normalize/group_neutralize/...)
  - economic meaning
  - prefer cold/niche operators
  - avoid IV (implied-volatility / options) operators
  - we may NOT click "Submit Alpha", but we MAY run the submit-readiness
    CHECK (`/alphas/{id}/check`) to confirm it WOULD pass.

Usage:
    python scripts/d0_mine.py simulate "<expr>" [universe] [neut] [decay] [trunc]
    python scripts/d0_mine.py check <alpha_id>
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
API = "https://api.worldquantbrain.com"


def _session():
    spec = importlib.util.spec_from_file_location(
        "cm", VENDOR / "core" / "credential_manager.py")
    cm_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cm_mod)
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        raise SystemExit("auth failed")
    return cm.session


def settings_d0(universe="TOP3000", neut="INDUSTRY", decay=4, trunc=0.08):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": universe,
        "delay": 0, "decay": decay, "neutralization": neut,
        "truncation": trunc, "pasteurization": "ON", "unitHandling": "VERIFY",
        "nanHandling": "OFF", "language": "FASTEXPR", "visualization": False,
        "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def simulate(session, expression, settings, poll_timeout=600, poll_interval=5):
    body = {"type": "REGULAR", "settings": settings, "regular": expression}
    for _ in range(5):
        r = session.post(f"{API}/simulations", json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 20)); continue
        break
    if r.status_code != 201:
        return {"ok": False, "stage": "submit", "status": r.status_code,
                "body": r.text[:400], "expression": expression}
    loc = r.headers.get("Location")
    t0 = time.time()
    while time.time() - t0 < poll_timeout:
        time.sleep(poll_interval)
        rp = session.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(20); continue
        if rp.status_code != 200:
            continue
        d = rp.json()
        st = d.get("status", "")
        if st == "COMPLETE":
            aid = d.get("alpha")
            ra = session.get(f"{API}/alphas/{aid}", timeout=30)
            return {"ok": True, "alpha_id": aid, "expression": expression,
                    "settings": settings, "alpha": ra.json()}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "sim", "status": st,
                    "message": d.get("message", "")[:400], "expression": expression}
    return {"ok": False, "stage": "timeout", "expression": expression}


def check_submit(session, alpha_id, poll_timeout=300, poll_interval=5):
    """Run the submit-readiness check WITHOUT submitting.

    GET /alphas/{id}/check triggers the full submission check suite
    (self-correlation, IS checks, etc.) and returns their PASS/FAIL.
    """
    t0 = time.time()
    while time.time() - t0 < poll_timeout:
        r = session.get(f"{API}/alphas/{alpha_id}/check", timeout=30)
        if r.status_code == 429:
            time.sleep(20); continue
        if r.status_code in (200, 201):
            try:
                return {"ok": True, "alpha_id": alpha_id, "data": r.json()}
            except Exception:
                return {"ok": True, "alpha_id": alpha_id, "raw": r.text[:1000]}
        if r.status_code == 204 or (r.text.strip() == ""):
            # still computing
            time.sleep(poll_interval); continue
        return {"ok": False, "alpha_id": alpha_id, "status": r.status_code,
                "body": r.text[:600]}
    return {"ok": False, "alpha_id": alpha_id, "stage": "timeout"}


def summarize(res):
    if not res.get("ok"):
        return res
    a = res["alpha"]; is_ = a.get("is", {}) or {}
    checks = is_.get("checks", []) or []
    return {
        "alpha_id": res["alpha_id"], "expression": res["expression"],
        "sharpe": is_.get("sharpe"), "turnover": is_.get("turnover"),
        "fitness": is_.get("fitness"), "returns": is_.get("returns"),
        "drawdown": is_.get("drawdown"), "margin": is_.get("margin"),
        "longCount": is_.get("longCount"), "shortCount": is_.get("shortCount"),
        "checks": [{"name": c.get("name"), "result": c.get("result"),
                    "value": c.get("value"), "limit": c.get("limit")}
                   for c in checks],
    }


if __name__ == "__main__":
    sess = _session()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "simulate":
        expr = sys.argv[2]
        uni = sys.argv[3] if len(sys.argv) > 3 else "TOP3000"
        neut = sys.argv[4] if len(sys.argv) > 4 else "INDUSTRY"
        decay = int(sys.argv[5]) if len(sys.argv) > 5 else 4
        trunc = float(sys.argv[6]) if len(sys.argv) > 6 else 0.08
        res = simulate(sess, expr, settings_d0(uni, neut, decay, trunc))
        print(json.dumps(summarize(res), indent=2))
    elif cmd == "check":
        print(json.dumps(check_submit(sess, sys.argv[2]), indent=2))
    else:
        print(__doc__)
