"""D0 sentiment round 3: amplify the WINNER signal found in round 2 --
QCM (high-confidence Ravenpack sentiment) REVERSAL. Smoothed QCM momentum
gave SH -1.10 => REVERSAL (-1*) gives +1.10, uncorrelated (sc -0.23),
low turnover. Now push it toward the D0 cutoff: sign-flipped, amplified,
gated, combined with QEP-reversal, window/neut sweep.
delay=0, no IV/option. Retries on concurrent-limit."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)
QCM="vec_avg(nws18_qcm)"; QEP="vec_avg(nws18_qep)"; SSC="vec_avg(nws18_ssc)"
SSE="vec_avg(nws18_sse)"; REL="vec_avg(nws18_relevance)"; NIP="vec_avg(nws18_nip)"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
def bf(x,n=60): return f"ts_backfill({x},{n})"
def sm(x,w): return f"ts_mean({bf(x)},{w})"
C=[
 # QCM reversal: window sweep (smoothing length)
 ("u_1_qcm_rev_w10", f"-{rk(sm(QCM,10))}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("u_2_qcm_rev_w20", f"-{rk(sm(QCM,20))}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("u_3_qcm_rev_w40", f"-{rk(sm(QCM,40))}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # QCM reversal MARKET neut (more return -> FIT)
 ("u_4_qcm_rev_mkt", f"-{rk(sm(QCM,20),'market')}", {"decay":6,"truncation":0.08,"neutralization":"MARKET"}),
 # QCM reversal amplified (concentrate conviction)
 ("u_5_qcm_amp", f"signed_power(-{rk(sm(QCM,20))}+0.0,3)", {"decay":4,"truncation":0.06,"neutralization":"SUBINDUSTRY"}),
 # QCM + QEP reversal combo (two high-quality sentiment reversals)
 ("u_6_qcm_qep", f"-{rk(sm(QCM,20))}-0.5*{rk(sm(QEP,20))}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # QCM + SSE reversal combo
 ("u_7_qcm_sse", f"-{rk(sm(QCM,20))}-0.5*{rk(sm(SSE,20))}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # QCM reversal gated on high relevance (trade only meaningful news)
 ("u_8_qcm_relgate", f"score=quantile(-{rk(sm(QCM,20))});\ngate=(ts_backfill({REL},5)>40);\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), 0)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # QCM reversal + price reversal (sentiment + price overreaction both fade)
 ("u_9_qcm_pricerev", f"-{rk(sm(QCM,20))}-0.5*{rk('ts_sum(returns,5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # QCM + QEP + SSE triple reversal
 ("u_10_triple", f"-{rk(sm(QCM,20))}-0.5*{rk(sm(QEP,20))}-0.5*{rk(sm(SSE,20))}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # combo MARKET neut + amp
 ("u_11_qcmqep_mkt_amp", f"signed_power(-{rk(sm(QCM,20),'market')}-0.5*{rk(sm(QEP,20),'market')},3)", {"decay":6,"truncation":0.08,"neutralization":"MARKET"}),
 # QCM reversal + quality (gross-profit, the best fundamental) -- two orthogonal D0 signals
 ("u_12_qcm_gp", f"-{rk(sm(QCM,20))}+0.5*{rk('divide(ts_backfill(sales,250),ts_backfill(assets,250))')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
]
def wname(r): return [c.get("name") for c in getattr(r,"checks",[]) if c.get("result")=="FAIL"]
def robust(sess,fam,expr,s):
    r=None
    for attempt in range(6):
        try:
            r=submit(sess,fam,expr,s)
            if (not r.ok) and r.error and ("CONCURRENT" in str(r.error) or "429" in str(r.error)):
                log.info(f"   concurrent wait 60s ({attempt+1}/6)"); time.sleep(60); continue
            return r
        except Exception as e: log.warning(f"   net {attempt+1}/6 {str(e)[:50]}"); time.sleep(25)
    return r
def main():
    cm=_load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  D0 SENT3 (QCM-reversal amplification)")
    out=REPO/"WQ_D0_SENT3.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== u [{i}/{len(C)}] {fam} ===")
        r=robust(cm.session,fam,expr,s)
        if r is None: continue
        if r.ok:
            try: sc,_,_=fetch_self_corr(cm.session,r.alpha_id,timeout_s=90); r.self_corr=sc
            except Exception: r.self_corr=None
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} sc={r.self_corr} FAIL={wname(r)}")
        else: log.warning(f"   FAILED: {str(r.error)[:110]}")
        res.append(r); json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def ok_(r): return (r.ok and not wname(r) and (r.self_corr is None or abs(r.self_corr)<0.7) and r.sharpe>1.25)
    oks=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*110); print(f"D0 SENT3: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        print(f"  {r.family:<20} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:70]}")
    print("="*110); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
