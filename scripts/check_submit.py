"""Run the WQ Brain PRE-SUBMIT CHECK on an alpha (does NOT submit).

  GET /alphas/{id}/check         -> submission check block (D0 thresholds)
  GET /alphas/{id}/correlations/self -> async SELF_CORRELATION value

Verdict = SUBMITTABLE iff every check is PASS (PENDING self-corr resolved < 0.7).

Usage: python scripts/check_submit.py <alpha_id> [<alpha_id> ...]
"""
import sys, json, time
sys.path.insert(0, "/home/user/Worldquant_Mining/scripts")
import wq_lib

API = "https://api.worldquantbrain.com"

def poll_check(s, aid, tries=40, interval=8):
    """Poll /check until SELF_CORRELATION (and any PENDING) resolves or budget out."""
    last = {}
    for i in range(tries):
        r = s.get(f"{API}/alphas/{aid}/check", timeout=30)
        if r.status_code != 200 or not r.text.strip():
            time.sleep(interval); continue
        last = r.json()
        checks = (last.get("is", {}) or {}).get("checks", []) or []
        pend = [c for c in checks if c.get("result") == "PENDING"]
        if not pend:
            return last, False
        time.sleep(interval)
    return last, True  # timed out with pending remaining

def main():
    s = wq_lib.auth()
    aids = sys.argv[1:]
    for aid in aids:
        a = s.get(f"{API}/alphas/{aid}", timeout=30).json()
        isb = a.get("is", {}) or {}
        st = a.get("settings", {}) or {}
        code = (a.get("regular", {}) or {}).get("code", "")
        print("="*92)
        print(f"alpha {aid}  d{st.get('delay')} {st.get('universe')} "
              f"{st.get('neutralization')} decay={st.get('decay')} trunc={st.get('truncation')}")
        print(f"  expr: {code}")
        print(f"  IS: sharpe={isb.get('sharpe')} turnover={isb.get('turnover')} "
              f"fitness={isb.get('fitness')} returns={isb.get('returns')} dd={isb.get('drawdown')} "
              f"long={isb.get('longCount')} short={isb.get('shortCount')}")
        chk, timed_out = poll_check(s, aid)
        checks = (chk.get("is", {}) or {}).get("checks", []) or []
        # also self-corr endpoint
        sc = s.get(f"{API}/alphas/{aid}/correlations/self", timeout=30)
        sc_val = None
        if sc.status_code == 200 and sc.text.strip():
            try:
                jd = sc.json()
                # schema: {"records":[...max...]} or {"max":..} -- print raw + extract max
                sc_val = jd
            except Exception:
                sc_val = sc.text[:300]
        print(f"  --- /check submission checks{' (TIMED OUT w/ pending)' if timed_out else ''} ---")
        verdict = True
        for c in checks:
            nm, res = c.get("name"), c.get("result")
            lim, val = c.get("limit"), c.get("value")
            extra = ""
            if lim is not None or val is not None:
                extra = f"  (limit={lim}, value={val})"
            print(f"    {res:<8} {nm}{extra}")
            if res not in ("PASS",):
                if not (nm == "MATCHES_COMPETITION"):  # competition match is informational
                    verdict = False
        print(f"  self-correlation endpoint: {json.dumps(sc_val)[:300] if sc_val is not None else '(empty)'}")
        print(f"  >>> VERDICT: {'SUBMITTABLE (all checks PASS)' if verdict else 'NOT yet submittable'}")
    print("="*92)

if __name__ == "__main__":
    main()
