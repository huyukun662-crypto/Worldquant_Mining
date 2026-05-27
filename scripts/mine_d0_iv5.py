"""D0 round 23: universe + dual-tenor levers to clear SH>2.0.
Plateau at ~1.95 on TOP3000. More liquid universes (TOP1000/500) have
cleaner options -> stronger IV signal. Also dual-tenor IV skew that
ADDS rather than dilutes. Base = g70 p3 (best). delay=0."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def q(x): return f"quantile({x})"
IV60="ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5)"
IV30="ts_backfill(implied_volatility_call_30 - implied_volatility_put_30, 5)"
IV90="ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 5)"
G70="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.70);"
def base(score,p=3): return f"score={score};\n{G70}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,{p}),5), -1)"
S60=f"{q(IV60)}"; SAVG=f"0.4*{q(IV30)}+0.4*{q(IV60)}+0.2*{q(IV90)}"
C=[
 # universe sweep on the g70 p3 winner
 ("z23_1_t1000", base(S60), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 ("z23_2_t500",  base(S60), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 ("z23_3_t200",  base(S60), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP200"}),
 ("z23_4_t1000_p4", base(S60,4), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 # multi-tenor averaged skew (more robust signal) on TOP3000 + TOP1000
 ("z23_5_avg_t3000", base(SAVG), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 ("z23_6_avg_t1000", base(SAVG), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 ("z23_7_avg_t500",  base(SAVG), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # IV30 skew (shorter tenor more reactive) universe sweep
 ("z23_8_iv30_t1000", base(f"{q(IV30)}"), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 # TOP1000 + MARKET neut (more return)
 ("z23_9_t1000_mkt", base(S60), {"decay":4,"truncation":0.03,"neutralization":"MARKET","universe":"TOP1000"}),
 # TOP1000 + INDUSTRY neut
 ("z23_10_t1000_ind", base(S60), {"decay":4,"truncation":0.02,"neutralization":"INDUSTRY","universe":"TOP1000"}),
 # TOP500 p4
 ("z23_11_t500_p4", base(S60,4), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # avg-tenor TOP1000 p4
 ("z23_12_avg_t1000_p4", base(SAVG,4), {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_IV5.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== z23 [{i}/{len(C)}] {fam} (univ={s['universe']}) ===")
        r=submit(cm.session,fam,expr,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} {r.alpha_id}")
        else: log.warning(f"   FAILED: {r.error[:130]}")
        json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    log.info("=== pass2 self-corr ===")
    for r in res:
        if not r.ok or not r.alpha_id: continue
        sc,top,stt=fetch_self_corr(cm.session,r.alpha_id,timeout_s=120); r.self_corr=sc
        if top: r.self_corr_peer=top.get("id"); r.self_corr_peer_sharpe=top.get("sharpe")
        log.info(f"   {r.alpha_id} sc={sc} ({stt})")
    json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def ok_(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7) and r.sharpe>2.0 and r.fitness>=1.3)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120); print(f"D0 IV5: SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:70]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
