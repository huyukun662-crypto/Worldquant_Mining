"""Run WorldQuant Brain's SUBMISSION check on an existing alpha id.

`/alphas/{id}/check` runs the full submission gate (LOW_SHARPE,
LOW_FITNESS, turnover, CONCENTRATED_WEIGHT, LOW_SUB_UNIVERSE_SHARPE,
SELF_CORRELATION, MATCHES_COMPETITION) WITHOUT actually submitting the
alpha. Use this to confirm a candidate is submittable before reporting.

Usage:  python scripts/check_submit.py <alpha_id> [<alpha_id> ...]
"""
from __future__ import annotations
import sys, time
from scripts.d0_batch import auth, API


def check(s, aid):
    # /check is computed async; poll until checks are populated / not PENDING-only
    for _ in range(40):
        r = s.get(f"{API}/alphas/{aid}/check", timeout=90)
        if r.status_code == 429:
            time.sleep(15); continue
        if r.status_code != 200:
            return {"ok": False, "code": r.status_code, "body": r.text[:300]}
        j = r.json()
        checks = (j.get("is") or {}).get("checks") or []
        if checks:
            return {"ok": True, "checks": checks}
        time.sleep(8)
    return {"ok": False, "error": "no checks populated"}


def main():
    s = auth()
    for aid in sys.argv[1:]:
        a = s.get(f"{API}/alphas/{aid}", timeout=30).json()
        code = (a.get("regular") or {}).get("code", "")
        isb = a.get("is") or {}
        print(f"\n===== {aid}  SH={isb.get('sharpe')} TO={isb.get('turnover')} "
              f"FIT={isb.get('fitness')} =====")
        print(f"  expr: {code}")
        res = check(s, aid)
        if not res["ok"]:
            print("  CHECK ERROR:", res); continue
        allpass = True
        for c in res["checks"]:
            r_ = c.get("result")
            if r_ == "FAIL":
                allpass = False
            print(f"  {c.get('name'):<24} {r_:<8} limit={c.get('limit')} value={c.get('value')}")
        # submittable = no FAIL (PENDING for self-corr is acceptable)
        verdict = "SUBMITTABLE (pending self-corr)" if allpass else "NOT submittable"
        print(f"  >>> {verdict}")


if __name__ == "__main__":
    main()
