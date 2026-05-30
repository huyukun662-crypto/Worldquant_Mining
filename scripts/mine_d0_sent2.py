"""D0 sentiment round 2: turnover-controlled forms (smoothing + gating)
of the genuinely-new sentiment signals. Raw daily sentiment was too
high-turnover (0.56-0.67). Smooth via ts_mean / ts_decay and gate on
relevance/buzz/earnings-flag to cut turnover toward submittable.
Retries on CONCURRENT_SIMULATION_LIMIT (waits instead of skipping).
delay=0, no option/IV fields."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)
SSC="vec_avg(nws18_ssc)"; SSE="vec_avg(nws18_sse)"; QEP="vec_avg(nws18_qep)"
BEE="vec_avg(nws18_bee)"; NIP="vec_avg(nws18_nip)"; QCM="vec_avg(nws18_qcm)"
REL="vec_avg(nws18_relevance)"; BER="vec_avg(nws18_ber)"
SCL="scl12_sentiment"; BUZZ="scl12_buzz"; SNT="snt_value"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
def bf(x,n=20): return f"ts_backfill({x},{n})"
C=[
 # --- SMOOTHED sentiment (ts_mean cuts turnover) momentum ---
 ("t_1_ssc_sm20",  f"{rk(f'ts_mean({bf(SSC,60)},20)')}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("t_2_qep_sm20",  f"{rk(f'ts_mean({bf(QEP,60)},20)')}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("t_3_qcm_sm20",  f"{rk(f'ts_mean({bf(QCM,60)},20)')}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("t_4_scl_sm20",  f"{rk(f'ts_mean({bf(SCL,60)},20)')}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- smoothed sentiment + price reversal (sentiment-confirmed reversal) ---
 ("t_5_ssc_x_rev", f"{rk(f'ts_mean({bf(SSC,60)},20)')}-0.5*{rk('ts_sum(returns,5)')}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- earnings sentiment gated on earnings-release flag ---
 ("t_6_bee_ergate",f"score=quantile(ts_mean({bf(BEE,60)},20));\ngate=(ts_backfill({BER},5)>0);\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), 0)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- relevance-gated Ravenpack sentiment (s_10 redo, multiple thresholds) ---
 ("t_7_ssc_rel30", f"score=quantile(ts_mean({bf(SSC,60)},10));\ngate=(ts_backfill({REL},5)>30);\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), 0)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("t_8_ssc_rel60", f"score=quantile(ts_mean({bf(SSC,60)},10));\ngate=(ts_backfill({REL},5)>60);\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), 0)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- smoothed sentiment MARKET neut ---
 ("t_9_ssc_mkt",   f"{rk(f'ts_mean({bf(SSC,60)},20)','market')}", {"decay":8,"truncation":0.08,"neutralization":"MARKET"}),
 ("t_10_scl_mkt",  f"{rk(f'ts_mean({bf(SCL,60)},20)','market')}", {"decay":8,"truncation":0.08,"neutralization":"MARKET"}),
 # --- sentiment dispersion: high sentiment + low buzz (underfollowed) ---
 ("t_11_ssc_lowbuzz", f"{rk(f'ts_mean({bf(SSC,60)},20)')}-0.3*{rk(f'ts_mean({bf(BUZZ,60)},20)')}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- combine Ravenpack + social (two sentiment sources) ---
 ("t_12_ssc_scl",  f"{rk(f'ts_mean({bf(SSC,60)},20)')}+{rk(f'ts_mean({bf(SCL,60)},20)')}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
]
def wname(r): return [c.get("name") for c in getattr(r,"checks",[]) if c.get("result")=="FAIL"]
def robust_submit(sess,fam,expr,s):
    for attempt in range(6):
        try:
            r=submit(sess,fam,expr,s)
            if (not r.ok) and r.error and ("CONCURRENT" in str(r.error) or "429" in str(r.error)):
                log.info(f"   concurrent-limit, wait 60s (try {attempt+1}/6)"); time.sleep(60); continue
            return r
        except Exception as e:
            log.warning(f"   net-err {attempt+1}/6: {str(e)[:55]}"); time.sleep(25)
    return r
def main():
    cm=_load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  D0 SENTIMENT round2 (smoothed+gated, concurrent-retry)")
    out=REPO/"WQ_D0_SENT2.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== t [{i}/{len(C)}] {fam} ===")
        r=robust_submit(cm.session,fam,expr,s)
        if r is None: continue
        if r.ok:
            try: sc,_,_=fetch_self_corr(cm.session,r.alpha_id,timeout_s=90); r.self_corr=sc
            except Exception: r.self_corr=None
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} sc={r.self_corr} FAIL={wname(r)}")
        else: log.warning(f"   FAILED: {str(r.error)[:110]}")
        res.append(r); json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def ok_(r): return (r.ok and not wname(r) and (r.self_corr is None or abs(r.self_corr)<0.7) and r.sharpe>1.25)
    oks=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*110); print(f"D0 SENT2: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        print(f"  {r.family:<18} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:70]}")
    print("="*110); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
