"""Reusable WQ Brain helpers: auth, simulate, fetch metrics, submit-check.

Used by the D0 cold-field/cold-operator mining effort. Not a pipeline; a
thin library so ad-hoc scripts stay short.
"""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = "https://api.worldquantbrain.com"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def auth():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        raise SystemExit("authentication failed")
    return cm.session


DEFAULTS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 0,
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


def simulate(session, expression: str, settings: dict | None = None,
             poll_timeout_s: int = 600, poll_interval_s: int = 5,
             verbose: bool = True) -> dict:
    s = dict(DEFAULTS)
    if settings:
        s.update(settings)
    body = {"type": "REGULAR", "settings": s, "regular": expression}
    for attempt in range(5):
        r = session.post(f"{BASE}/simulations", json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            if verbose:
                print(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait)
            continue
        break
    if r.status_code != 201:
        return {"ok": False, "stage": "submit", "status": r.status_code,
                "body": r.text[:500], "expression": expression, "settings": s}
    progress_url = r.headers.get("Location")
    if not progress_url:
        return {"ok": False, "stage": "submit", "error": "no Location",
                "expression": expression, "settings": s}
    t0 = time.time()
    last = ""
    while time.time() - t0 < poll_timeout_s:
        time.sleep(poll_interval_s)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30)
            continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if verbose and st != last:
            print(f"   status={st} ({int(time.time()-t0)}s)")
            last = st
        if st == "COMPLETE":
            aid = data.get("alpha")
            ra = session.get(f"{BASE}/alphas/{aid}", timeout=30)
            return {"ok": True, "alpha_id": aid, "expression": expression,
                    "settings": s, "alpha": ra.json() if ra.status_code == 200 else None}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "simulation", "status": st,
                    "message": data.get("message", "")[:500],
                    "data": data, "expression": expression, "settings": s}
    return {"ok": False, "stage": "timeout", "expression": expression, "settings": s}


def is_metrics(alpha_json: dict) -> dict:
    isb = (alpha_json or {}).get("is") or {}
    checks = isb.get("checks") or []
    return {
        "sharpe": isb.get("sharpe"),
        "turnover": isb.get("turnover"),
        "fitness": isb.get("fitness"),
        "returns": isb.get("returns"),
        "drawdown": isb.get("drawdown"),
        "margin": isb.get("margin"),
        "longCount": isb.get("longCount"),
        "shortCount": isb.get("shortCount"),
        "checks": {c.get("name"): c.get("result") for c in checks},
        "checks_full": checks,
    }


def submit_check(session, alpha_id: str, poll_timeout_s: int = 300,
                 poll_interval_s: int = 5, verbose: bool = True) -> dict:
    """GET /alphas/{id}/check  -> runs the submission checks (self-correlation,
    prod-correlation, etc.) WITHOUT actually submitting. Returns the check
    block. This does NOT consume the Submit Alpha quota the way POST does.
    """
    url = f"{BASE}/alphas/{alpha_id}/check"
    t0 = time.time()
    while time.time() - t0 < poll_timeout_s:
        r = session.get(url, timeout=30)
        if r.status_code == 429:
            time.sleep(15)
            continue
        # While checks compute, WQ returns 200 with retry-after-ish empty body
        retry_after = r.headers.get("Retry-After")
        try:
            data = r.json()
        except Exception:
            data = {}
        if retry_after:
            if verbose:
                print(f"   check pending; retry after {retry_after}s")
            time.sleep(float(retry_after))
            continue
        return {"status": r.status_code, "data": data}
    return {"status": "timeout"}
