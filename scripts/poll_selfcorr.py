"""Patiently resolve SELF_CORRELATION for given alpha_ids.

Polls GET /alphas/{id}/correlations/self (numeric max) and GET /alphas/{id}/check
(SELF_CORRELATION PASS/FAIL) until resolved or budget exhausted.
"""
import sys, json, time
sys.path.insert(0, "/home/user/Worldquant_Mining/scripts")
import wq_lib
API = "https://api.worldquantbrain.com"

def parse_max(jd):
    """Self-corr payload schema: {'schema':{...}, 'records':[[...]] , 'max':?}.
    Records rows typically [alpha_id, ..., correlation]. Return max |corr|."""
    if not isinstance(jd, dict):
        return None, jd
    if "max" in jd and isinstance(jd["max"], (int, float)):
        return jd["max"], jd
    recs = jd.get("records") or []
    cols = [c.get("name") for c in (jd.get("schema", {}) or {}).get("properties", [])] if jd.get("schema") else []
    ci = None
    for i, c in enumerate(cols):
        if c and "corr" in c.lower():
            ci = i; break
    vals = []
    for r in recs:
        if isinstance(r, list):
            if ci is not None and ci < len(r) and isinstance(r[ci], (int, float)):
                vals.append(r[ci])
            else:
                vals += [x for x in r if isinstance(x, (int, float))]
    return (max(vals, key=abs) if vals else None), jd

def main():
    s = wq_lib.auth()
    aids = sys.argv[1:]
    for aid in aids:
        print(f"\n==== {aid} : resolving self-correlation ====", flush=True)
        resolved = False
        for i in range(60):  # up to ~60*12 = 12 min
            r = s.get(f"{API}/alphas/{aid}/correlations/self", timeout=30)
            chk = s.get(f"{API}/alphas/{aid}/check", timeout=30)
            sc_res = None
            if chk.status_code == 200 and chk.text.strip():
                checks = (chk.json().get("is", {}) or {}).get("checks", []) or []
                c = next((x for x in checks if x.get("name") == "SELF_CORRELATION"), None)
                if c: sc_res = c.get("result")
            mx = None
            if r.status_code == 200 and r.text.strip():
                try:
                    mx, raw = parse_max(r.json())
                except Exception as e:
                    raw = r.text[:200]
            done = sc_res in ("PASS", "FAIL") or (mx is not None)
            print(f"  [{i:02d}] check.SELF_CORRELATION={sc_res}  max_self_corr={mx}", flush=True)
            if done and sc_res in ("PASS","FAIL"):
                # also dump the records once
                try:
                    print("  self-corr payload:", json.dumps(r.json())[:600], flush=True)
                except Exception:
                    pass
                print(f"  >>> {aid}: SELF_CORRELATION={sc_res}  max={mx}", flush=True)
                resolved = True
                break
            time.sleep(12)
        if not resolved:
            print(f"  >>> {aid}: self-correlation still unresolved after budget", flush=True)

if __name__ == "__main__":
    main()
