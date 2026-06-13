"""SERIAL, code-verified D0 measurement (no concurrency, no shared-session bug).

Runs each (tag, expr, settings) ONE AT A TIME, polls its own Location, fetches
/alphas/{id}, ASSERTS regular.code == expr, records TRUE metrics. Saves JSON.
"""
import sys, json, time, re
sys.path.insert(0, "/home/user/Worldquant_Mining/scripts")
import wq_lib
API = "https://api.worldquantbrain.com"
def norm(s): return re.sub(r"\s+","", s or "")

def one(s, expr, settings):
    body={"type":"REGULAR","settings":settings,"regular":expr}
    loc=None
    for a in range(15):
        r=s.post(f"{API}/simulations",json=body,timeout=30)
        if r.status_code==429:
            time.sleep(float(r.headers.get("Retry-After") or 0) or min(15+a*10,90)); continue
        if r.status_code==201: loc=r.headers.get("Location"); break
        return {"error":f"post-{r.status_code}:{r.text[:150]}"}
    if not loc: return {"error":"429-exhausted"}
    t0=time.time()
    while time.time()-t0<480:
        time.sleep(5)
        rp=s.get(loc,timeout=30)
        if rp.status_code!=200: continue
        d=rp.json(); st=d.get("status","")
        if st=="COMPLETE":
            aid=d.get("alpha"); a=s.get(f"{API}/alphas/{aid}",timeout=30).json()
            code=(a.get("regular",{}) or {}).get("code",""); isb=a.get("is",{}) or {}
            checks=isb.get("checks",[]) or []
            return {"alpha_id":aid,"code_match":norm(code)==norm(expr),"code":code,
                    "sharpe":isb.get("sharpe"),"turnover":isb.get("turnover"),
                    "fitness":isb.get("fitness"),"returns":isb.get("returns"),
                    "longCount":isb.get("longCount"),"shortCount":isb.get("shortCount"),
                    "checks":[(c.get("name"),c.get("result"),c.get("limit"),c.get("value")) for c in checks]}
        if st in ("ERROR","FAILED","WARNING"): return {"error":f"sim-{st}:{str(d.get('message'))[:150]}"}
    return {"error":"poll-timeout"}

def main():
    spec=json.load(open(sys.argv[1])); out=sys.argv[2] if len(sys.argv)>2 else "_serial_out.json"
    s=wq_lib.auth(); rows=[]
    for j in spec:
        st=dict(wq_lib.FIXED); st.update(wq_lib.D0_DEFAULT); st.update(j.get("settings",{})); st["delay"]=0
        print(f"\n[{j['tag']}] {j['expr']}  ({st['universe']} d0 decay={st['decay']} trunc={st['truncation']} {st['neutralization']})", flush=True)
        res=one(s,j["expr"],st)
        if "error" in res:
            print(f"   ERR: {res['error']}", flush=True); rows.append({"tag":j["tag"],"expr":j["expr"],**res})
        else:
            cm="OK" if res["code_match"] else "***MISMATCH***"
            print(f"   [{cm}] SH={res['sharpe']} TO={res['turnover']} FIT={res['fitness']} alpha={res['alpha_id']}", flush=True)
            rows.append({"tag":j["tag"],"expr":j["expr"],"settings":j.get("settings",{}),**res})
        json.dump(rows,open(out,"w"),indent=1)
        time.sleep(4)
    # ranked summary
    ok=[r for r in rows if r.get("code_match") and r.get("sharpe") is not None]
    ok.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    print("\n==== TRUE (code-verified, serial) leaderboard by |SH| ====", flush=True)
    for r in ok:
        print(f"   SH={r['sharpe']:+.2f} TO={r['turnover']:.3f} FIT={r['fitness']:+.2f}  {r['tag']:<22} {r['expr'][:55]}", flush=True)
    print(f"wrote {out}", flush=True); print("ALLDONE", flush=True)

if __name__=="__main__": main()
