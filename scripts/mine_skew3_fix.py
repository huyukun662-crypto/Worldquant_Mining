import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
SPECS=[
 ("sk_rank","rank(ts_decay_linear(group_neutralize(-1*ts_mean(signed_power(returns,3),20), subindustry), 4))",0.08),
 ("sk_wins","zscore(ts_decay_linear(group_neutralize(-1*ts_mean(signed_power(winsorize(returns,std=4),3),20), subindustry), 4))",0.08),
 ("sk_winsig","zscore(winsorize(ts_decay_linear(group_neutralize(-1*ts_mean(signed_power(returns,3),20), subindustry), 4), std=3))",0.08),
 ("sk_tr03","zscore(ts_decay_linear(group_neutralize(-1*ts_mean(signed_power(returns,3),20), subindustry), 4))",0.03),
 ("sk_rank_wins","rank(ts_decay_linear(group_neutralize(-1*ts_mean(signed_power(winsorize(returns,std=4),3),20), subindustry), 4))",0.08),
 ("sk_w15","rank(ts_decay_linear(group_neutralize(-1*ts_mean(signed_power(winsorize(returns,std=4),3),15), subindustry), 4))",0.08),
 ("sk_w30","rank(ts_decay_linear(group_neutralize(-1*ts_mean(signed_power(winsorize(returns,std=4),3),30), subindustry), 6))",0.08),
]
def selfcorr(aid):
    for _ in range(18):
        r=s.get(f"{API}/alphas/{aid}/correlations/self",timeout=30)
        if r.status_code==200 and r.text.strip():
            rows=r.json().get("records",[])
            return ('%.3f'%max(abs(x[-1]) for x in rows)) if rows else 'empty'
        time.sleep(5)
    return 'pending'
def run(name,expr,tr):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":"USA",
      "universe":"TOP3000","delay":1,"decay":0,"neutralization":"SUBINDUSTRY","truncation":tr,
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
            tag=" **LOWCORR-CLEAN**" if (sh>=1.25 and not nf and sc and sc!='pending' and float(sc)<0.5) else ""
            print("[%s] SH=%.2f FIT=%.2f TO=%.3f selfcorr=%s id=%s FAIL=%s%s"%(name,sh,isb.get('fitness') or 0,isb.get('turnover') or 0,sc,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:70]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for sp in SPECS:
    try: run(*sp)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
