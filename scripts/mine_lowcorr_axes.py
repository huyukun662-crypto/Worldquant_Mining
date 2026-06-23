import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
SPECS=[
 ("rrev_n5_T1k","rank(-ts_rank(returns, 5))","TOP1000","SUBINDUSTRY",18,0.08),
 ("rrev_n9_T1k","rank(-ts_rank(returns, 9))","TOP1000","SUBINDUSTRY",18,0.08),
 ("rrev_n7_T3k","rank(-ts_rank(returns, 7))","TOP3000","SUBINDUSTRY",18,0.08),
 ("rrev_n7_T2k","rank(-ts_rank(returns, 7))","TOP2000","SUBINDUSTRY",18,0.08),
 ("rrev_n7_dc24","rank(-ts_rank(returns, 7))","TOP1000","SUBINDUSTRY",24,0.08),
 ("rrev_n11_T1k","rank(-ts_rank(returns, 11))","TOP1000","SUBINDUSTRY",18,0.08),
 ("rrev_n7_IND","rank(-ts_rank(returns, 7))","TOP1000","INDUSTRY",18,0.08),
 ("rrev_vn","group_neutralize(-ts_rank(returns, 7)/(ts_std_dev(returns,20)+0.001), subindustry)","TOP1000","SUBINDUSTRY",18,0.08),
 ("avd_n14_T1k","normalize(reverse(ts_av_diff(close, 14)))","TOP1000","SUBINDUSTRY",8,0.08),
 ("avd_n10_T1k","normalize(reverse(ts_av_diff(close, 10)))","TOP1000","SUBINDUSTRY",12,0.08),
 ("avd_n21_T1k","normalize(reverse(ts_av_diff(close, 21)))","TOP1000","SUBINDUSTRY",18,0.08),
 ("avd_multi","normalize(add(reverse(ts_av_diff(close,10)), reverse(ts_av_diff(close,21))))","TOP1000","SUBINDUSTRY",12,0.08),
 ("illiq_v2","add(-zscore(ts_decay_linear(ts_mean(divide(subtract(high, low), multiply(close, volume)), 500), 200)), -zscore(ts_decay_linear(ts_av_diff(close, 10), 6)))","TOP3000","NONE",4,0.08),
]
def selfcorr(aid):
    for _ in range(22):
        r=s.get(f"{API}/alphas/{aid}/correlations/self",timeout=30)
        if r.status_code==200 and r.text.strip():
            rows=r.json().get("records",[])
            return ('%.3f'%max(abs(x[-1]) for x in rows)) if rows else 'empty'
        time.sleep(5)
    return 'pending'
def run(name,expr,univ,neut,dc,tr):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":"USA",
      "universe":univ,"delay":1,"decay":dc,"neutralization":neut,"truncation":tr,
      "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON","language":"FASTEXPR",
      "visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M"},"regular":expr}
    for _ in range(80):
        r=s.post(f"{API}/simulations",json=body,timeout=30)
        if r.status_code==429: time.sleep(12); continue
        break
    if r.status_code!=201:
        print(f"[{name}] submit {r.status_code}: {r.text[:100]}",flush=True); return
    loc=r.headers["Location"]; t0=time.time()
    while time.time()-t0<2400:
        time.sleep(8); rp=s.get(loc,timeout=30)
        if rp.status_code!=200: continue
        d=rp.json(); st=d.get("status","")
        if st=="COMPLETE":
            aid=d["alpha"]; a=s.get(f"{API}/alphas/{aid}",timeout=30).json()
            isb=a.get("is") or {}; ch=isb.get("checks") or []
            nf=[c["name"] for c in ch if c.get("result")=="FAIL"]
            sh=isb.get("sharpe") or 0
            sc=selfcorr(aid) if (sh>=1.25 and not nf) else None
            tag=" **LOWCORR-CLEAN**" if (sh>=1.5 and not nf and sc and sc!='pending' and float(sc)<0.5) else ""
            print("[%s] SH=%.2f FIT=%.2f TO=%.3f selfcorr=%s id=%s FAIL=%s%s"%(name,sh,isb.get('fitness') or 0,isb.get('turnover') or 0,sc,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:80]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for sp in SPECS:
    try: run(*sp)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
