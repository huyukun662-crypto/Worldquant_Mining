import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
W=lambda sig,dc=6: f"zscore(ts_decay_linear(group_neutralize({sig}, subindustry), {dc}))"
EM="anl4_afv4_eps_mean"; EH="anl4_afv4_eps_high"; EL="anl4_afv4_eps_low"; EN="anl4_afv4_eps_number"; DV="anl4_afv4_div_mean"; CF="anl4_afv4_cfps_mean"
VV="group_neutralize(-1*ts_std_dev(ts_std_dev(returns,5),20), subindustry)"
SPECS={
 "eps_disp":W(f"rank(-1*({EH}-{EL})/(abs({EM})+0.01))"),
 "eps_cover":W(f"rank(ts_delta({EN},60))"),
 "eps_rev":W(f"rank(ts_mean(ts_delta({EM},20),60))"),
 "div_rev":W(f"rank(ts_mean(ts_delta({DV},20),60))"),
 "cfps_rev":W(f"rank(ts_mean(ts_delta({CF},20),60))"),
 "disp_rev":W(f"rank(-1*({EH}-{EL})/(abs({EM})+0.01)) + rank(ts_mean(ts_delta({EM},20),60))"),
 "skew_w30":W(f"add(zscore(group_neutralize(-1*ts_mean(signed_power(returns,3),30), subindustry)), zscore({VV}))"),
 "kurt_w30":W(f"add(zscore(group_neutralize(-1*ts_mean(signed_power(returns,4),30), subindustry)), zscore({VV}))"),
 "rev_skew":W(f"rank(ts_mean(ts_delta({EM},20),60)) + zscore(group_neutralize(-1*ts_mean(signed_power(returns,3),20), subindustry))"),
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
      "universe":"TOP1000","delay":1,"decay":0,"neutralization":"SUBINDUSTRY","truncation":0.08,
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
