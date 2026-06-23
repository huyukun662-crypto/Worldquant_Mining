import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
# CORRECT construction: add() inside ts_decay_linear, each leg separately group_neutralized
def GN(x): return f"zscore(group_neutralize({x}, subindustry))"
def BL(legs,dc=4): return f"zscore(ts_decay_linear(add({', '.join(legs) if len(legs)==2 else legs[0]}), {dc}))" if False else "zscore(ts_decay_linear("+ "add("+legs[0]+", "+legs[1]+")" +f", {dc}))"
SK20="-1*ts_mean(signed_power(returns,3),20)"; SK10="-1*ts_mean(signed_power(returns,3),10)"
KU20="-1*ts_mean(signed_power(returns,4),20)"; KU30="-1*ts_mean(signed_power(returns,4),30)"
VV="-1*ts_std_dev(ts_std_dev(returns,5),20)"; PK="-1*ts_std_dev(log(high/low),20)"
SPECS={
 # NEW higher-moment combos on TOP3000 (correct construction, distinct from omKvxe9m/pw6EREV3)
 "kurt_park":BL([GN(KU20),GN(PK)]),                # kurtosis + Parkinson (NEW pairing)
 "skew_park":BL([GN(SK20),GN(PK)]),                # skewness + Parkinson
 "kurt30_vv":BL([GN(KU30),GN(VV)]),                # kurtosis w30 + vol-of-vol
 "skew10_vv":BL([GN(SK10),GN(VV)]),                # short-window skew + vol-of-vol
 "skew_kurt":BL([GN(SK20),GN(KU20)]),              # skewness + kurtosis (pure moment combo)
 "skew_kurt_park":"zscore(ts_decay_linear(add(add("+GN(SK20)+", "+GN(KU20)+"), "+GN(PK)+"), 4))",  # 3-moment
}
def realsc(aid):
    for _ in range(14):
        r=s.get(f"{API}/alphas/{aid}/correlations/self",timeout=30)
        if r.status_code==200 and r.text.strip():
            rows=r.json().get("records",[])
            return round(max([abs(x[5]) for x in rows],default=0.0),3) if rows else None
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
            rc=realsc(aid) if (abs(sh)>=1.25 and not nf) else None
            tag=" **SUBMITTABLE(realcorr<0.65)**" if (sh>=1.25 and not nf and isinstance(rc,float) and rc<0.65) else ""
            print("[%s] SH=%.2f FIT=%.2f TO=%.3f REALcorr=%s id=%s FAIL=%s%s"%(name,sh,isb.get('fitness') or 0,isb.get('turnover') or 0,rc,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:70]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for name,expr in SPECS.items():
    try: run(name,expr)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
