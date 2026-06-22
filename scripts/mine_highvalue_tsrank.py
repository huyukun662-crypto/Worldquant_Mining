import sys, time, traceback
sys.path.insert(0,'/home/user/Worldquant_Mining')
from scripts.d0_batch import auth
s=auth(); API="https://api.worldquantbrain.com"
W=lambda sig,dc=6: f"zscore(ts_decay_linear(group_neutralize({sig}, subindustry), {dc}))"
SPECS={
 "m_total_tr":W("rank(ts_rank(fscore_bfl_total, 40))"),
 "m_mom_tr":W("rank(ts_rank(fscore_bfl_momentum, 40))"),
 "m_comp_tr":W("rank(ts_rank(composite_factor_score_derivative, 40))"),
 "s_score_tr":W("rank(ts_rank(snt1_cored1_score, 40))"),
 "s_rev_mom":W("rank(ts_mean(ts_delta(snt1_d1_netearningsrevision, 20), 60))"),
 "s_rec_tr":W("rank(ts_rank(snt1_d1_netrecpercent, 40))"),
 "s_focus_tr":W("rank(ts_rank(snt1_d1_dynamicfocusrank, 40))"),
 "s_surprise_tr":W("rank(ts_rank(snt1_d1_earningssurprise, 40))"),
 "m_s_comp":W("rank(ts_rank(fscore_bfl_total, 40)) + rank(ts_rank(snt1_cored1_score, 40))"),
 "sent_combo":W("rank(ts_rank(snt1_cored1_score, 40)) + rank(ts_rank(snt1_d1_netrecpercent, 40))"),
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
            ok=(abs(sh)>=1.25 and not nf)
            rc=realsc(aid) if ok else None
            y20=yr2020(aid) if ok else None
            tag=" **HIVAL-CLEAN(corr%s,2020=%s)**"%(rc,y20) if (sh>=1.25 and not nf and isinstance(rc,float) and rc<0.7) else ""
            print("[%s] SH=%.2f TO=%.3f corr=%s 2020=%s id=%s FAIL=%s%s"%(name,sh,isb.get('turnover') or 0,rc,y20,aid,nf,tag),flush=True); return
        if st in ("ERROR","FAILED"):
            print(f"[{name}] {st}: {str(d.get('message',''))[:70]}",flush=True); return
    print(f"[{name}] timeout",flush=True)
for name,expr in SPECS.items():
    try: run(name,expr)
    except Exception: traceback.print_exc()
    time.sleep(2)
print("DONE",flush=True)
