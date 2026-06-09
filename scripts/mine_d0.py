"""Batch D0 (delay=0) alpha miner / checker for WorldQuant Brain.

Submits a list of (expression, settings) candidates to `/simulations`
concurrently (in waves, respecting the account's ~3 concurrent-sim cap),
polls each to COMPLETE, fetches `/alphas/{id}` IS metrics + checks, and
prints a ranked table.

This is a CHECK tool: it never calls the Submit-Alpha endpoint. It only
runs simulations so we can confirm a candidate would PASS submission
(all IS checks PASS, Sharpe/Fitness above the delay-0 limits) BEFORE
reporting.

Delay-0 IS check limits observed on this account (YW92315):
    LOW_SHARPE   limit 2.0   (sharpe   must be >  2.0)
    LOW_FITNESS  limit 1.3   (fitness  must be >  1.3)
    HIGH_TURNOVER limit 0.7  (turnover must be <  0.7)
    LOW_TURNOVER  limit 0.01 (turnover must be >  0.01)
    LOW_SUB_UNIVERSE_SHARPE  (sub-universe sharpe must clear a small floor)

Usage:
    python scripts/mine_d0.py candidates.json
where candidates.json is a list of {"expression": str, "settings": {...}}.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

REPO = Path(__file__).resolve().parent.parent
API = "https://api.worldquantbrain.com"

# Delay-0 default simulation settings.
BASE_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 0,
    "decay": 6,
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

POLL_TIMEOUT = 420
POLL_INTERVAL = 6
WAVE = 3  # concurrent simulations


def auth() -> requests.Session:
    s = requests.Session()
    creds = json.loads((REPO / "credential.txt").read_text())
    s.auth = HTTPBasicAuth(creds[0], creds[1])
    r = s.post(f"{API}/authentication", timeout=20)
    if r.status_code != 201:
        raise SystemExit(f"auth failed {r.status_code}: {r.text[:200]}")
    return s


def submit_one(s: requests.Session, expr: str, settings: dict) -> dict:
    try:
        return _submit_one(s, expr, settings)
    except Exception as e:  # network/transient -> never kill the batch
        full = dict(BASE_SETTINGS); full.update(settings or {})
        return {"ok": False, "expression": expr, "settings": full,
                "error": f"exc: {type(e).__name__}: {str(e)[:150]}"}


def poll_check(s: requests.Session, aid: str, tries: int = 30) -> list | None:
    """Poll /alphas/{id}/check until the IS check block populates.
    Returns the list of check dicts (incl. real SELF_CORRELATION) or None."""
    for _ in range(tries):
        rc = s.get(f"{API}/alphas/{aid}/check", timeout=60)
        if rc.status_code == 429:
            time.sleep(15); continue
        txt = (rc.text or "").strip()
        if not txt:
            time.sleep(5); continue
        try:
            checks = ((rc.json().get("is") or {}).get("checks")) or []
        except Exception:
            time.sleep(5); continue
        # wait until self-correlation resolves out of PENDING
        if checks and all(c.get("result") != "PENDING" for c in checks):
            return checks
        if checks:
            time.sleep(5)
    return checks if 'checks' in dir() else None


def _submit_one(s: requests.Session, expr: str, settings: dict) -> dict:
    full = dict(BASE_SETTINGS)
    full.update(settings or {})
    body = {"type": "REGULAR", "settings": full, "regular": expr}
    # POST (with 429 backoff)
    for _ in range(6):
        r = s.post(f"{API}/simulations", json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 20)); continue
        break
    if r.status_code != 201:
        return {"ok": False, "expression": expr, "settings": full,
                "error": f"submit-{r.status_code}: {r.text[:200]}"}
    loc = r.headers.get("Location")
    if not loc:
        return {"ok": False, "expression": expr, "settings": full,
                "error": "no Location"}
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        rp = s.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(20); continue
        if rp.status_code != 200:
            continue
        d = rp.json(); st = d.get("status")
        if st == "COMPLETE":
            aid = d.get("alpha")
            ra = s.get(f"{API}/alphas/{aid}", timeout=30)
            if ra.status_code != 200:
                return {"ok": False, "expression": expr, "settings": full,
                        "alpha_id": aid, "error": f"alpha-get-{ra.status_code}"}
            isb = (ra.json().get("is") or {})
            # Real submit gate: poll /alphas/{id}/check (this computes
            # SELF_CORRELATION against the submitted pool; the plain
            # /alphas read leaves it PENDING).
            checks = poll_check(s, aid) or (isb.get("checks") or [])
            failed = [c["name"] for c in checks if c.get("result") == "FAIL"]
            self_corr = next((c.get("value") for c in checks
                              if c.get("name") == "SELF_CORRELATION"), None)
            return {
                "ok": True, "expression": expr, "settings": full,
                "alpha_id": aid,
                "sharpe": isb.get("sharpe"), "turnover": isb.get("turnover"),
                "fitness": isb.get("fitness"), "returns": isb.get("returns"),
                "drawdown": isb.get("drawdown"),
                "margin": isb.get("margin"),
                "longCount": isb.get("longCount"),
                "shortCount": isb.get("shortCount"),
                "self_corr": self_corr,
                "checks": checks,
                "failed_checks": failed,
                "pass_submittable": len(failed) == 0,
            }
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "expression": expr, "settings": full,
                    "error": f"sim-{st}: {str(d.get('message',''))[:200]}"}
    return {"ok": False, "expression": expr, "settings": full, "error": "timeout"}


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "D0_RESULTS.json"
    cands = json.loads(Path(src).read_text())
    s = auth()
    print(f"authenticated; submitting {len(cands)} candidates "
          f"in waves of {WAVE}", flush=True)

    results = []
    for i in range(0, len(cands), WAVE):
        wave = cands[i:i + WAVE]
        with cf.ThreadPoolExecutor(max_workers=WAVE) as ex:
            futs = {ex.submit(submit_one, s, c["expression"],
                              c.get("settings", {})): c for c in wave}
            for fut in cf.as_completed(futs):
                r = fut.result()
                results.append(r)
                if r.get("ok"):
                    mark = "PASS-SUBMIT" if r["pass_submittable"] else \
                           f"fail:{','.join(r['failed_checks'])}"
                    sc = r.get("self_corr")
                    scs = f" selfcorr={sc:.2f}" if isinstance(sc, (int, float)) else ""
                    print(f"  OK  SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
                          f"FIT={r['fitness']:+.3f}{scs}  [{mark}]  {r['alpha_id']}  "
                          f"{r['expression'][:60]}", flush=True)
                else:
                    print(f"  ERR {r['error'][:80]}  {r['expression'][:60]}",
                          flush=True)
        Path(out).write_text(json.dumps(results, indent=2))

    # Rank by submittability then sharpe
    results.sort(key=lambda r: (r.get("pass_submittable", False),
                                r.get("sharpe") or -99), reverse=True)
    print("\n" + "=" * 100)
    print(f"{'SH':>7}{'TO':>7}{'FIT':>7}{'sub?':>6}  alpha_id    expression")
    for r in results:
        if not r.get("ok"):
            continue
        sub = "YES" if r["pass_submittable"] else "no"
        print(f"{r['sharpe']:7.3f}{r['turnover']:7.3f}{r['fitness']:7.3f}"
              f"{sub:>6}  {r['alpha_id']:<11} {r['expression'][:60]}")
    print("=" * 100)
    Path(out).write_text(json.dumps(results, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
