import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
WRAP=lambda sig,dc:f"zscore(ts_decay_linear(group_neutralize({sig}, subindustry), {dc}))"
# brand-new orthogonal signal families (NO close/open intraday reuse)
SIG={
 # overnight gap reversal (orthogonal to intraday close/open)
 "gap_rev":"(-1 * winsorize((open/ts_delay(close,1) - 1), std=2) / (ts_std_dev((open/ts_delay(close,1) - 1), 20) + 0.001))",
 # close position within daily high-low range, reversal
 "range_pos":"(-1 * winsorize(((close - low)/(high - low + 0.001) - 0.5), std=2))",
 # VWAP deviation reversal (vol-normalized)
 "vwap_rev":"(-1 * winsorize((close/vwap - 1), std=2) / (ts_std_dev((close/vwap - 1), 20) + 0.001))",
 # weekly (5-day) reversal, vol-normalized
 "wk_rev":"(-1 * winsorize((close/ts_delay(close,5) - 1), std=2) / (ts_std_dev((close/ts_delay(close,1) - 1), 20) + 0.001))",
 # Amihud illiquidity (abs ret / dollar-vol), cross-sectional premium
 "illiq":"ts_mean(abs(close/ts_delay(close,1) - 1)/(volume*close + 1), 20)",
 # high-low range expansion vs its own baseline (vol timing), reversal
 "range_exp":"(-1 * (ts_std_dev(high/low - 1, 5) - ts_mean(ts_std_dev(high/low - 1, 5), 20)))",
 # volume surprise interacted with same-day return (reversal on high-vol moves)
 "vol_surp":"(-1 * winsorize((close/ts_delay(close,1) - 1), std=2) * ts_rank(volume, 20))",
 # 3-day reversal vol-normalized (between intraday and weekly)
 "d3_rev":"(-1 * winsorize((close/ts_delay(close,3) - 1), std=2) / (ts_std_dev((close/ts_delay(close,1) - 1), 20) + 0.001))",
}
SPECS=[(k,6,"MARKET") for k in SIG]  # decay6, MARKET neut (winning combo)
def selfcorr(aid):
    for _ in range(25):
        r=s.get(f"{API}/alphas/{aid}/correlations/self",timeout=30)
        if r.status_code==200 and r.text.strip():
            try: return round(max([abs(x[-1]) for x in r.json().get("records",[])],default=0.0),3)
            except: return None
        time.sleep(5)
    return None
def run(name,dc,neut):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":"USA",
      "universe":"TOP3000","delay":1,"decay":0,"neutralization":neut,"truncation":0.08,
      "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON","language":"FASTEXPR",
      "visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M"},"regular":WRAP(SIG[name],dc)}
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
            sc = selfcorr(aid) if sh>=1.25 else None
            tag=""
            if sh>=1.25 and not nf and (sc is not None and sc<0.5): tag=" **LOWCORR-CLEAN**"
            print("[%s] SH=%.2f FIT=%.2f TO=%.3f selfcorr=%s id=%s FAIL=%s%s"%(name,sh,isb.get('fitness') or 0,isb.get('turnover') or 0,sc,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:90]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for sp in SPECS:
    try: run(*sp)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
