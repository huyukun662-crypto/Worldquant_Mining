"""D1 factor miner + submittability checker for WorldQuant Brain.

Self-contained: authenticates from repo-root credential.txt, submits a list
of (expression, settings) candidates to /simulations with bounded
concurrency, polls the {"progress": x} bodies to completion, fetches each
alpha's IS metrics + checks, and then runs the *submission* checks via
GET /alphas/{id}/check (without ever submitting).

Usage:
    python scripts/d1_miner.py            # runs the built-in candidate batch
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

API = "https://api.worldquantbrain.com"
REPO = Path(__file__).resolve().parent.parent


def auth() -> requests.Session:
    u, p = json.load(open(REPO / "credential.txt"))
    s = requests.Session()
    s.auth = HTTPBasicAuth(u, p)
    r = s.post(f"{API}/authentication", timeout=20)
    assert r.status_code == 201, (r.status_code, r.text[:200])
    return s


FIXED = {
    "instrumentType": "EQUITY", "region": "USA", "delay": 1,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P0Y0M",
    "maxTrade": "OFF",
}


def settings(universe="TOP1000", neut="SUBINDUSTRY", decay=4, trunc=0.08):
    s = dict(FIXED)
    s.update(universe=universe, neutralization=neut, decay=decay, truncation=trunc)
    return s


def post_sim(s, expr, st):
    body = {"type": "REGULAR", "settings": st, "regular": expr}
    for _ in range(6):
        r = s.post(f"{API}/simulations", json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 15)); continue
        if r.status_code == 201:
            return r.headers.get("Location"), None
        return None, f"{r.status_code}:{r.text[:200]}"
    return None, "429-exhausted"


def poll(s, loc, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = s.get(loc, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 10)); continue
        if r.status_code != 200:
            time.sleep(5); continue
        d = r.json()
        if "alpha" in d or d.get("status") in ("COMPLETE", "ERROR", "FAILED", "WARNING"):
            return d
        # body is {"progress": x}
        time.sleep(float(r.headers.get("Retry-After") or 5))
    return {"status": "TIMEOUT"}


def fetch_alpha(s, aid):
    return s.get(f"{API}/alphas/{aid}", timeout=30).json()


def submission_check(s, aid, timeout=300):
    """GET /alphas/{id}/check runs submission checks WITHOUT submitting."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = s.get(f"{API}/alphas/{aid}/check", timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 10)); continue
        if r.status_code != 200:
            return {"error": f"{r.status_code}:{r.text[:200]}"}
        d = r.json()
        # while running, the in/is checks may be PENDING with retry-after
        ra = r.headers.get("Retry-After")
        if ra:
            time.sleep(float(ra)); continue
        return d
    return {"error": "check-timeout"}


def run_batch(candidates, max_concurrent=3):
    s = auth()
    print(f"authenticated; submitting {len(candidates)} candidates "
          f"(concurrency={max_concurrent})", flush=True)
    inflight = []   # list of dicts {idx, expr, st, loc}
    done = []
    i = 0
    while i < len(candidates) or inflight:
        # fill
        while i < len(candidates) and len(inflight) < max_concurrent:
            expr, st = candidates[i]
            loc, err = post_sim(s, expr, st)
            if err:
                print(f"[{i}] SUBMIT-ERR {err}  {expr[:60]}", flush=True)
                done.append({"idx": i, "expr": expr, "st": st, "error": err})
            else:
                print(f"[{i}] submitted {loc.rsplit('/',1)[-1]}  {expr[:60]}", flush=True)
                inflight.append({"idx": i, "expr": expr, "st": st, "loc": loc})
            i += 1
        # poll inflight once each
        still = []
        for job in inflight:
            r = s.get(job["loc"], timeout=30)
            if r.status_code != 200:
                still.append(job); continue
            d = r.json()
            if not ("alpha" in d or d.get("status") in ("COMPLETE","ERROR","FAILED","WARNING")):
                still.append(job); continue
            # finished
            aid = d.get("alpha")
            if not aid:
                print(f"[{job['idx']}] FAILED {d.get('status')} {str(d)[:150]}", flush=True)
                done.append({**job, "result": d})
                continue
            a = fetch_alpha(s, aid)
            isb = a.get("is", {}) or {}
            checks = isb.get("checks", []) or []
            npass = sum(1 for c in checks if c.get("result") == "PASS")
            print(f"[{job['idx']}] DONE {aid} SH={isb.get('sharpe')} "
                  f"TO={isb.get('turnover')} FIT={isb.get('fitness')} "
                  f"checks={npass}/{len(checks)}  {job['expr'][:50]}", flush=True)
            done.append({**job, "alpha_id": aid, "is": isb})
        inflight = still
        if inflight:
            time.sleep(8)
    return s, done


if __name__ == "__main__":
    # placeholder; candidates are driven by callers
    print("import and call run_batch(candidates)")
