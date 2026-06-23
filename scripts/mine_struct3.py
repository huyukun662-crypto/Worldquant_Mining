import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
W=lambda sig,dc: f"zscore(ts_decay_linear(group_neutralize({sig}, subindustry), {dc}))"
SIG={
 "accdist":"ts_mean(((close - low) - (high - close))/(high - low + 0.001), 20)",
 "volaccel":"(-1 * ts_mean(volume, 5) / (ts_mean(volume, 60) + 1))",
 "winrate":"(-1 * ts_mean(sign(returns), 22))",
 "longmom":"(ts_delay(close, 20) / (ts_delay(close, 250) + 0.001) - 1)",
 "downvol":"(-1 * ts_sum(abs(returns) - returns, 20))",
 "kyle":"(-1 * ts_corr(abs(returns), volume, 20))",
 "mfvol":"(-1 * ts_mean(returns * volume, 10))",
 "rvchg":"ts_corr(returns, ts_delta(volume, 1), 20)",
 "rangetr":"(-1 * ts_delta(ts_mean((high - low)/(close + 0.001), 5), 20))",
 "cvwap":"(-1 * ts_mean((close - vwap)/(vwap + 0.001), 15))",
}
DC={k:4 for k in SIG}
def selfcorr(aid):
    for _ in range(18):
        r=s.get(f"{API}/alphas/{aid}/correlations/self",timeout=30)
        if r.status_code==200 and r.text.strip():
            rows=r.json().get("records",[])
            return ('%.3f'%max(abs(x[-1]) for x in rows)) if rows else 'empty'
        time.sleep(5)
    return 'pending'
def run(name):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":"USA",
      "universe":"TOP3000","delay":1,"decay":0,"neutralization":"SUBINDUSTRY","truncation":0.08,
      "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON","language":"FASTEXPR",
      "visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M"},"regular":W(SIG[name],DC[name])}
    for _ in range(80):
        r=s.post(f"{API}/simulations",json=body,timeout=30)
        if r.status_code==429: time.sleep(12); continue
        break
    if r.status_code!=201:
        print(f"[{name}] submit {r.status_code}: {r.text[:90]}",flush=True); return
    loc=r.headers["Location"]; t0=time.time()
    while time.time()-t0<3000:
        time.sleep(10); rp=s.get(loc,timeout=30)
        if rp.status_code!=200: continue
        d=rp.json(); st=d.get("status","")
        if st=="COMPLETE":
            aid=d["alpha"]; a=s.get(f"{API}/alphas/{aid}",timeout=30).json()
            isb=a.get("is") or {}; ch=isb.get("checks") or []
            nf=[c["name"] for c in ch if c.get("result")=="FAIL"]
            sh=isb.get("sharpe") or 0
            sc=selfcorr(aid) if (abs(sh)>=1.25 and not nf) else None
            tag=" **LOWCORR-CLEAN**" if (sh>=1.25 and not nf and sc and sc!='pending' and float(sc)<0.5) else ""
            print("[%s] SH=%.2f FIT=%.2f TO=%.3f selfcorr=%s id=%s FAIL=%s%s"%(name,sh,isb.get('fitness') or 0,isb.get('turnover') or 0,sc,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:72]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for name in SIG:
    try: run(name)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
