"""PARANOID single-simulation verifier — guards against alpha-id cross-talk.

Runs ONE simulation, polls its OWN Location URL, then fetches /alphas/{id}
and ASSERTS the returned regular.code equals the submitted expression before
trusting any metric. Prints true IS metrics + /check summary.

Usage: python scripts/isolated_verify.py "EXPR" universe decay truncation [neut]
"""
import sys, json, time, re
sys.path.insert(0, "/home/user/Worldquant_Mining/scripts")
import wq_lib
API = "https://api.worldquantbrain.com"

def norm(s): return re.sub(r"\s+", "", s or "")

def main():
    expr = sys.argv[1]
    universe = sys.argv[2] if len(sys.argv) > 2 else "TOP500"
    decay = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    trunc = float(sys.argv[4]) if len(sys.argv) > 4 else 0.05
    neut = sys.argv[5] if len(sys.argv) > 5 else "SUBINDUSTRY"
    s = wq_lib.auth()
    settings = dict(wq_lib.FIXED); settings.update(wq_lib.D0_DEFAULT)
    settings.update({"universe":universe,"delay":0,"decay":decay,
                     "truncation":trunc,"neutralization":neut})
    body = {"type":"REGULAR","settings":settings,"regular":expr}
    print(f"SUBMIT (delay=0 {universe} decay={decay} trunc={trunc} {neut}): {expr}", flush=True)
    # POST with backoff
    loc = None
    for attempt in range(15):
        r = s.post(f"{API}/simulations", json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 0) or min(15+attempt*10,90)); continue
        if r.status_code == 201:
            loc = r.headers.get("Location"); break
        print(f"  POST {r.status_code}: {r.text[:200]}"); return
        break
    if not loc:
        print("  no Location (429-exhausted)"); return
    print(f"  Location={loc}", flush=True)
    # Poll THIS location only
    aid = None
    t0 = time.time()
    while time.time()-t0 < 480:
        time.sleep(5)
        rp = s.get(loc, timeout=30)
        if rp.status_code != 200: continue
        d = rp.json(); st = d.get("status","")
        if st == "COMPLETE": aid = d.get("alpha"); break
        if st in ("ERROR","FAILED","WARNING"):
            print(f"  sim {st}: {d.get('message')}"); return
    if not aid:
        print("  poll timeout"); return
    a = s.get(f"{API}/alphas/{aid}", timeout=30).json()
    code = (a.get("regular",{}) or {}).get("code","")
    match = norm(code) == norm(expr)
    isb = a.get("is",{}) or {}
    print(f"  alpha_id={aid}", flush=True)
    print(f"  CODE-MATCH={match}  alpha.regular.code={code!r}", flush=True)
    if not match:
        print("  *** MISMATCH: alpha id cross-contaminated; metrics below are NOT this expr ***", flush=True)
    print(f"  TRUE IS: sharpe={isb.get('sharpe')} turnover={isb.get('turnover')} "
          f"fitness={isb.get('fitness')} returns={isb.get('returns')} "
          f"L/S={isb.get('longCount')}/{isb.get('shortCount')}", flush=True)
    # /check
    for _ in range(20):
        rc = s.get(f"{API}/alphas/{aid}/check", timeout=30)
        if rc.status_code==200 and rc.text.strip():
            checks=(rc.json().get("is",{}) or {}).get("checks",[]) or []
            if len(checks)>=8:
                sc=next((c for c in checks if c["name"]=="SELF_CORRELATION"),None)
                print(f"  CHECK ({len(checks)}): " + ", ".join(f"{c['name']}={c['result']}" for c in checks), flush=True)
                if sc and sc.get("result")!="PENDING":
                    nonpass=[c for c in checks if c['result']!='PASS']
                    print(f"  >>> SUBMITTABLE={len(nonpass)==0 and match}", flush=True)
                    break
        time.sleep(10)
    print("DONE", flush=True)

if __name__ == "__main__":
    main()
