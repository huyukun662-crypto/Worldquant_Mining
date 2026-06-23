import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
# PROVEN Option recipe (WjpNW2Qd: SH1.31 clean corr0.418): zscore(ts_backfill(ts_delta(IV, K), 250)) heavy decay, TOP1000, trunc 0.01
# explore other IV tenors + IV structures (term structure, IV-HV spread, put-call skew momentum)
B=lambda inner: "zscore(ts_backfill(%s, 250))"%inner
# tuple: (expr, decay, trunc, univ, neut) -- decay=128 in SETTINGS (WjpNW2Qd's clean recipe: heavy decay cuts turnover)
SPECS={
 "iv_c30":(B("ts_delta(implied_volatility_call_30, 10)"),128,0.01,"TOP1000","SUBINDUSTRY"),
 "iv_p60":(B("ts_delta(implied_volatility_put_60, 10)"),128,0.01,"TOP1000","SUBINDUSTRY"),
 "iv_c120":(B("ts_delta(implied_volatility_call_120, 10)"),128,0.01,"TOP1000","SUBINDUSTRY"),
 # IV-HV spread (variance risk premium) momentum
 "iv_vrp":(B("ts_delta(implied_volatility_call_30 - historical_volatility_30, 10)"),128,0.01,"TOP1000","SUBINDUSTRY"),
 # put-call skew momentum
 "iv_skew":(B("ts_delta(implied_volatility_put_30 - implied_volatility_call_30, 10)"),128,0.01,"TOP1000","SUBINDUSTRY"),
 # WjpNW2Qd at TOP3000/SECTOR -> distinct lower-corr instance
 "iv_c60_t3k":(B("ts_delta(implied_volatility_call_60, 10)"),128,0.05,"TOP3000","SECTOR"),
 # longer delta window
 "iv_c60_d20":(B("ts_delta(implied_volatility_call_60, 20)"),128,0.01,"TOP1000","SUBINDUSTRY"),
 # lighter decay variant to compare
 "iv_c60_d64":(B("ts_delta(implied_volatility_call_60, 10)"),64,0.01,"TOP1000","SUBINDUSTRY"),
}
def realsc(aid):
    for _ in range(15):
        r=s.get(f"{API}/alphas/{aid}/correlations/self",timeout=30)
        if r.status_code==200 and r.text.strip():
            rows=r.json().get("records",[]); return round(max([abs(x[5]) for x in rows],default=0.0),3) if rows else None
        time.sleep(5)
    return None
def yr2020(aid):
    for _ in range(10):
        r=s.get(f"{API}/alphas/{aid}/recordsets/yearly-stats",timeout=30)
        if r.status_code==200 and r.text.strip():
            j=r.json(); recs=j.get('records',[]); props=[p['name'] for p in j.get('schema',{}).get('properties',[])]
            si=props.index('sharpe') if 'sharpe' in props else 1
            for row in recs:
                if str(row[0])[:4]=='2020': return row[si]
            return None
        time.sleep(4)
    return None
def run(name,expr,dc,tr,univ,neut):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":"USA","universe":univ,"delay":1,"decay":dc,
      "neutralization":neut,"truncation":tr,"pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON",
      "language":"FASTEXPR","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M"},"regular":expr}
    for _ in range(80):
        r=s.post(f"{API}/simulations",json=body,timeout=30)
        if r.status_code==429: time.sleep(12); continue
        break
    if r.status_code!=201:
        print(f"[{name}] submit {r.status_code}: {r.text[:80]}",flush=True); return
    loc=r.headers["Location"]; t0=time.time()
    while time.time()-t0<5400:
        time.sleep(12); rp=s.get(loc,timeout=30)
        if rp.status_code!=200: continue
        d=rp.json(); st=d.get("status","")
        if st=="COMPLETE":
            aid=d["alpha"]; a=s.get(f"{API}/alphas/{aid}",timeout=30).json()
            isb=a.get("is") or {}; ch=isb.get("checks") or []
            nf=[c["name"] for c in ch if c.get("result")=="FAIL"]; sh=isb.get("sharpe") or 0
            ok=(sh>=1.25 and not nf); rc=realsc(aid) if ok else None; y=yr2020(aid) if ok else None
            tag=" **OPT-CLEAN(corr%s,2020=%s)**"%(rc,y) if ok and isinstance(rc,float) and rc<0.7 else ""
            print("[%s] SH=%.2f TO=%.3f FIT=%.2f corr=%s 2020=%s id=%s FAIL=%s%s"%(name,sh,isb.get('turnover') or 0,isb.get('fitness') or 0,rc,y,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:60]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
only=set(sys.argv[1:])
for name,v in SPECS.items():
    if only and name not in only: continue
    try: run(name,*v)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
