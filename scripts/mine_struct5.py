import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
VV="group_neutralize(-1*ts_std_dev(ts_std_dev(returns,5),20), subindustry)"
W=lambda sig: f"zscore(ts_decay_linear(group_neutralize({sig}, subindustry), 4))"
B=lambda sig: f"zscore(ts_decay_linear(add(zscore(group_neutralize({sig}, subindustry)), zscore({VV})), 4))"
SPECS={
 "kurt4":W("(-1*ts_mean(signed_power(returns,4),20))"),
 "kurt4_blend":B("(-1*ts_mean(signed_power(returns,4),20))"),
 "semivar":W("(-1*ts_std_dev(abs(returns)-returns,20))"),
 "semivar_blend":B("(-1*ts_std_dev(abs(returns)-returns,20))"),
 "cubemom_blend":B("(-1*ts_mean(signed_power(ts_delta(close,1),3),15))"),
 "coskew":W("(-1*ts_corr(returns, signed_power(returns,2), 20))"),
 "semivar_ratio":W("(-1*ts_std_dev(abs(returns)-returns,20)/(ts_std_dev(returns,20)+0.001))"),
 "hskew_blend":B("(-1*ts_mean(signed_power(returns,3),10))"),
}
def selfcorr(aid):
    for _ in range(16):
        r=s.get(f"{API}/alphas/{aid}/correlations/self",timeout=30)
        if r.status_code==200 and r.text.strip():
            rows=r.json().get("records",[])
            return ('%.3f'%max(abs(x[-1]) for x in rows)) if rows else 'empty'
        time.sleep(5)
    return 'pending'
def run(name,expr):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":"USA",
      "universe":"TOP3000","delay":1,"decay":0,"neutralization":"SUBINDUSTRY","truncation":0.08,
      "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON","language":"FASTEXPR",
      "visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M"},"regular":expr}
    for _ in range(80):
        r=s.post(f"{API}/simulations",json=body,timeout=30)
        if r.status_code==429: time.sleep(12); continue
        break
    if r.status_code!=201:
        print(f"[{name}] submit {r.status_code}: {r.text[:88]}",flush=True); return
    loc=r.headers["Location"]; t0=time.time()
    while time.time()-t0<3300:
        time.sleep(10); rp=s.get(loc,timeout=30)
        if rp.status_code!=200: continue
        d=rp.json(); st=d.get("status","")
        if st=="COMPLETE":
            aid=d["alpha"]; a=s.get(f"{API}/alphas/{aid}",timeout=30).json()
            isb=a.get("is") or {}; ch=isb.get("checks") or []
            nf=[c["name"] for c in ch if c.get("result")=="FAIL"]
            sh=isb.get("sharpe") or 0
            sc=selfcorr(aid) if (sh>=1.25 and not nf) else None
            tag=" **LOWCORR-CLEAN**" if (sh>=1.4 and not nf and sc and sc!='pending' and float(sc)<0.5) else ""
            print("[%s] SH=%.2f FIT=%.2f TO=%.3f selfcorr=%s id=%s FAIL=%s%s"%(name,sh,isb.get('fitness') or 0,isb.get('turnover') or 0,sc,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:70]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for name,expr in SPECS.items():
    try: run(name,expr)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
