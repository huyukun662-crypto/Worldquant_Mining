import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
W=lambda sig,dc=5: f"zscore(ts_decay_linear(group_neutralize({sig}, subindustry), {dc}))"
SI="mdl177_2_liquidityriskfactor_si_ratio"; DTC="mdl177_5shortsentimentfactor_days_to_cover"; UTIL="mdl177_5shortsentimentfactor_act_util"
SPECS={
 "si_anom":W(f"rank(-1*ts_zscore({SI},60))"),
 "days_cover":W(f"rank(-1*ts_mean({DTC},20))"),
 "util":W(f"rank(-1*ts_mean({UTIL},20))"),
 "si_news":W("rank(-1*ts_zscore(news_short_interest,60))"),
 "sent_rev":W("rank(-1*ts_mean(snt_social_value,5))"),
 "sent_mom":W("rank(ts_mean(scl12_sentiment,20))"),
 "buzz_delta":W("rank(ts_delta(scl12_buzz,5))"),
 "si_sent":W(f"rank(-1*ts_zscore({SI},60)) + rank(-1*ts_mean(snt_social_value,5))"),
 "si_dtc":W(f"rank(-1*ts_zscore({SI},60)) + rank(-1*ts_mean({DTC},20))"),
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
      "universe":"TOP1000","delay":1,"decay":0,"neutralization":"SUBINDUSTRY","truncation":0.08,
      "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON","language":"FASTEXPR",
      "visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M"},"regular":expr}
    for _ in range(80):
        r=s.post(f"{API}/simulations",json=body,timeout=30)
        if r.status_code==429: time.sleep(12); continue
        break
    if r.status_code!=201:
        print(f"[{name}] submit {r.status_code}: {r.text[:90]}",flush=True); return
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
            sc=selfcorr(aid) if (abs(sh)>=1.25 and not nf) else None
            tag=" **SUBMITTABLE-NEW**" if (sh>=1.25 and not nf and sc and sc!='pending' and float(sc)<0.5) else ""
            print("[%s] SH=%.2f FIT=%.2f TO=%.3f selfcorr=%s id=%s FAIL=%s%s"%(name,sh,isb.get('fitness') or 0,isb.get('turnover') or 0,sc,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:72]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for name,expr in SPECS.items():
    try: run(name,expr)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
