import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
W=lambda sig,dc: f"zscore(ts_decay_linear(group_neutralize({sig}, subindustry), {dc}))"
# brand-NEW structures (NO ts_rank-of-returns, NO close/open, NO av_diff, NO illiquidity)
SIG={
 # price-volume correlation divergence
 "pv_corr":"(-1 * ts_corr(close, volume, 20))",
 "pv_corr_d":"(-1 * ts_corr(ts_delta(close, 1), ts_delta(volume, 1), 20))",
 "pv_rankcorr":"(-1 * ts_corr(ts_rank(close, 20), ts_rank(volume, 20), 20))",
 # Bollinger z-score mean reversion (standardized deviation, NOT av_diff)
 "boll_z":"(-1 * (close - ts_mean(close, 20)) / (ts_std_dev(close, 20) + 0.001))",
 # Kaufman efficiency ratio reversal (trend efficiency)
 "kaufman":"(-1 * ts_delta(close, 10) / (ts_sum(abs(ts_delta(close, 1)), 10) + 0.001))",
 # Parkinson range-based volatility reversal
 "parkinson":"(-1 * ts_std_dev(log(high / low), 20))",
 # vol-of-vol
 "volvol":"(-1 * ts_std_dev(ts_std_dev(returns, 5), 20))",
 # days-since-high recency (ts_arg_max)
 "argmax":"ts_arg_max(close, 20)",
 # return skewness reversal
 "skew":"(-1 * ts_skewness(returns, 22))",
 # return kurtosis
 "kurt":"(-1 * ts_kurtosis(returns, 22))",
 # signed-power momentum (different nonlinearity)
 "spow":"(-1 * signed_power(ts_delta(close, 5)/ts_delta(close,5), 0.5))",
 # downside vs upside volume imbalance
 "volimb":"(-1 * (ts_mean(volume, 5) - ts_mean(volume, 22)) / (ts_std_dev(volume, 22) + 1))",
}
DC={"pv_corr":4,"pv_corr_d":4,"pv_rankcorr":4,"boll_z":6,"kaufman":6,"parkinson":4,"volvol":4,"argmax":4,"skew":4,"kurt":4,"spow":4,"volimb":4}
def selfcorr(aid):
    for _ in range(20):
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
    while time.time()-t0<1500:
        time.sleep(8); rp=s.get(loc,timeout=30)
        if rp.status_code!=200: continue
        d=rp.json(); st=d.get("status","")
        if st=="COMPLETE":
            aid=d["alpha"]; a=s.get(f"{API}/alphas/{aid}",timeout=30).json()
            isb=a.get("is") or {}; ch=isb.get("checks") or []
            nf=[c["name"] for c in ch if c.get("result")=="FAIL"]
            sh=isb.get("sharpe") or 0
            sc=selfcorr(aid) if (abs(sh)>=1.25 and not nf) else None
            tag=" **LOWCORR-CLEAN**" if (sh>=1.5 and not nf and sc and sc!='pending' and float(sc)<0.5) else ""
            print("[%s] SH=%.2f FIT=%.2f TO=%.3f selfcorr=%s id=%s FAIL=%s%s"%(name,sh,isb.get('fitness') or 0,isb.get('turnover') or 0,sc,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:75]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for name in SIG:
    try: run(name)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
