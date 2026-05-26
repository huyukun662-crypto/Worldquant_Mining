"""D0 round 14: z-score/Bollinger mean-reversion + ts_regression trend
+ fine-tuned best-combo. Untried operators: ts_zscore on price,
ts_regression, ts_std_dev normalization. delay=0, no options.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
ZC="ts_zscore(close,20)"                       # 20d price z-score (Bollinger)
ZC10="ts_zscore(close,10)"
TREND="ts_regression(close, ts_step(20), 20)"  # 20d price trend slope
RET="returns"; R5="ts_sum(returns,5)"
VWAPDEV="divide(close-vwap,vwap)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
BV="divide(ts_backfill(bookvalue_ps,250),close)"
C=[
 # 1. Bollinger mean-reversion (fade price above 20d mean)
 ("u14_1_zscore20_rev", f"-{rk(ZC)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 2. faster z-score10 reversion
 ("u14_2_zscore10_rev", f"-{rk(ZC10)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 3. z-score reversion + capex quality
 ("u14_3_zscore_capex", f"-{rk(ZC)}+0.5*{rk(INV)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 4. z-score reversion volume-gated
 ("u14_4_zscore_volgate", f"sig=-{rk(ZC)};\ngate=ts_rank(volume,20)>0.85;\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 5. trend-slope reversal (fade strong trends)
 ("u14_5_trend_rev", f"-{rk(TREND)}", {"decay":6,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 6. z-score + vwap + reversal triple
 ("u14_6_triple_rev", f"-{rk(ZC)}-0.5*{rk(VWAPDEV)}-0.5*{rk(R5)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 7. z-score reversion + capex + value (best-combo style)
 ("u14_7_zscore_capex_val", f"-{rk(ZC)}+0.5*{rk(INV)}+0.3*{rk(BV)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 8. z-score reversion MARKET neut high trunc (FIT)
 ("u14_8_zscore_mkt", f"-{rk(ZC,'subindustry')}", {"decay":4,"truncation":0.12,"neutralization":"MARKET"}),
 # 9. z-score10 + capex, volume-gated
 ("u14_9_z10_capex_gate", f"sig=-{rk(ZC10)}+0.5*{rk(INV)};\ngate=ts_rank(volume,20)>0.85;\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 10. z-score reversion amplified
 ("u14_10_zscore_amp", f"signed_power(-{rk(ZC)},3)", {"decay":4,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 11. z-score + capex + value, MARKET neut (return->FIT)
 ("u14_11_combo_mkt", f"-{rk(ZC,'subindustry')}+0.5*{rk(INV,'subindustry')}+0.3*{rk(BV,'subindustry')}",
   {"decay":4,"truncation":0.12,"neutralization":"MARKET"}),
 # 12. z-score reversion decay8 TOP1000
 ("u14_12_zscore_t1000", f"-{rk(ZC)}", {"decay":8,"truncation":0.08,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_MEANREV.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== u14 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr.replace(chr(10),' | ')}")
        r=submit(cm.session,fam,expr,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} {r.alpha_id}")
        else: log.warning(f"   FAILED: {r.error[:140]}")
        json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    log.info("=== pass2 self-corr ===")
    for r in res:
        if not r.ok or not r.alpha_id: continue
        sc,top,stt=fetch_self_corr(cm.session,r.alpha_id,timeout_s=120); r.self_corr=sc
        if top: r.self_corr_peer=top.get("id"); r.self_corr_peer_sharpe=top.get("sharpe")
        log.info(f"   {r.alpha_id} sc={sc} ({stt})")
    json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def ok_(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7)
                        and r.sharpe>2.0 and r.fitness>=1.3)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D0 MEANREV (bar 2.0/1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
