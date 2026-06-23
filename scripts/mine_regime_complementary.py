import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
INTRA="-1 * ts_sum(winsorize(((close / open) - 1), std=2) / (ts_std_dev(((close / open) - 1), 20) + 0.001), 1)"
SPECS={
 "intra_mkt":("zscore(ts_decay_linear(group_neutralize(("+INTRA+"), subindustry), 6))","TOP3000","MARKET",0),
 "rr_n5_T2k":("rank(-ts_rank(returns, 5))","TOP2000","SUBINDUSTRY",18),
 "rr_n10_T2k":("rank(-ts_rank(returns, 10))","TOP2000","SUBINDUSTRY",18),
 "wk_rev":("zscore(ts_decay_linear(group_neutralize(-1*winsorize((close/ts_delay(close,5)-1),std=2)/(ts_std_dev((close/ts_delay(close,1)-1),20)+0.001), subindustry), 6))","TOP3000","SUBINDUSTRY",0),
 "illiq":("add(add(-zscore(ts_decay_linear(ts_mean(divide(subtract(high, low), multiply(close, volume)), 1000), 400)), -zscore(ts_decay_linear(ts_av_diff(close, 5), 5))), multiply(0.5, -zscore(ts_decay_linear(ts_av_diff(close, 15), 8))))","TOP3000","NONE",0),
 "longmom":("rank(ts_rank(close/ts_delay(close,230), 40))","TOP1000","SUBINDUSTRY",10),
 "hl_range":("zscore(ts_decay_linear(group_neutralize(-1*ts_av_diff((high-low)/(close+0.001), 20), subindustry), 6))","TOP3000","SUBINDUSTRY",0),
}
def realsc(aid):
    for _ in range(12):
        r=s.get(f"{API}/alphas/{aid}/correlations/self",timeout=30)
        if r.status_code==200 and r.text.strip():
            rows=r.json().get("records",[])
            return round(max([abs(x[5]) for x in rows],default=0.0),3) if rows else None
        time.sleep(5)
    return None
def yr2020(aid):
    for _ in range(8):
        r=s.get(f"{API}/alphas/{aid}/recordsets/yearly-stats",timeout=30)
        if r.status_code==200 and r.text.strip():
            j=r.json(); recs=j.get('records',[]); props=[p['name'] for p in j.get('schema',{}).get('properties',[])]
            si=props.index('sharpe') if 'sharpe' in props else 1
            for row in recs:
                if str(row[0])[:4]=='2020': return row[si]
            return None
        time.sleep(4)
    return None
def run(name,expr,univ,neut,dc):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":"USA",
      "universe":univ,"delay":1,"decay":dc,"neutralization":neut,"truncation":0.08,
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
            rc=realsc(aid) if (abs(sh)>=1.25 and not nf) else None
            y20=yr2020(aid) if (abs(sh)>=1.25 and not nf) else None
            tag=""
            if sh>=1.25 and not nf and isinstance(rc,float) and rc<0.7 and isinstance(y20,(int,float)) and y20>0.3:
                tag=" **COMPLEMENTARY(2020+ & corr<0.7)**"
            print("[%s] SH=%.2f TO=%.3f REALcorr=%s SH2020=%s id=%s FAIL=%s%s"%(name,sh,isb.get('turnover') or 0,rc,y20,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:70]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for name,(expr,univ,neut,dc) in SPECS.items():
    try: run(name,expr,univ,neut,dc)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
