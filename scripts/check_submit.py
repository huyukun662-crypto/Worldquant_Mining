"""Confirm an alpha is submittable WITHOUT submitting it.

GET /alphas/{id}/check runs the full submission-check suite (the same
checks the Submit button gates on: IS sharpe/fitness/turnover, sub-universe
sharpe, concentrated weight, self-correlation, ladder, etc.) and returns
PASS/FAIL/PENDING per check. We never POST to the submit endpoint.

Usage:
    python scripts/check_submit.py <alpha_id> [<alpha_id> ...]
"""
from __future__ import annotations
import json, sys, time
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path

API = "https://api.worldquantbrain.com"
REPO = Path(__file__).resolve().parent.parent


def auth():
    u, p = json.load(open(REPO / "credential.txt"))
    s = requests.Session(); s.auth = HTTPBasicAuth(u, p)
    r = s.post(f"{API}/authentication", timeout=20)
    assert r.status_code == 201, (r.status_code, r.text[:200])
    return s


def check(s, aid, timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = s.get(f"{API}/alphas/{aid}/check", timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 10)); continue
        if r.status_code != 200:
            return {"error": f"{r.status_code}:{r.text[:200]}"}
        ra = r.headers.get("Retry-After")
        if ra:  # checks still running
            time.sleep(float(ra)); continue
        return r.json()
    return {"error": "timeout"}


def summarize(aid, data):
    isb = (data.get("is") or {})
    checks = isb.get("checks") or data.get("checks") or []
    print(f"\n=== alpha {aid} ===")
    fails = []
    for c in checks:
        name = c.get("name"); res = c.get("result")
        print(f"  {name:<28} {res:<8} value={c.get('value')} limit={c.get('limit')}")
        if res == "FAIL":
            fails.append(name)
    submittable = checks and all(c.get("result") in ("PASS", "PENDING") for c in checks) \
        and not any(c.get("result") == "FAIL" for c in checks)
    print(f"  --> {'SUBMITTABLE (no FAILs)' if submittable else 'NOT submittable; FAIL: ' + ','.join(fails)}")
    return submittable


if __name__ == "__main__":
    s = auth()
    for aid in sys.argv[1:]:
        d = check(s, aid)
        if "error" in d:
            print(f"{aid}: ERROR {d['error']}"); continue
        summarize(aid, d)
