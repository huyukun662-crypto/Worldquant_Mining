"""D0 round 16: custom pv13 relationship groups + multi-layer transforms.

pv13 ships purpose-built grouping fields (pure-play relationship
clusters). Neutralizing the best signals within these tighter groups
+ multi-layer ts_rank(ts_zscore(...)) transforms may extract more
alpha than standard subindustry. delay=0, no options.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
GRP="pv13_h_min2_focused_pureplay_3000_sector"
GRP2="pv13_r2_min5_3000_sector"
def rk(x,g): return f"group_rank({x},{g})"
ZC="ts_zscore(close,20)"; R5="ts_sum(returns,5)"; RET="returns"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
CUST="ts_backfill(rel_ret_cust,5)"
C=[
 # 1. reversal+capex in pure-play groups
 ("c16_1_revcapex_pp", f"-{rk(R5,GRP)}+0.5*{rk(INV,GRP)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 2. z-score reversion in pure-play groups
 ("c16_2_zscore_pp", f"-{rk(ZC,GRP)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 3. multi-layer: ts_rank of cross-sectional reversal
 ("c16_3_multilayer", f"-ts_rank({rk(R5,'subindustry')},10)", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 4. ts_rank(ts_zscore(returns)) reversal
 ("c16_4_tsrank_z", f"-ts_rank(ts_zscore(returns,20),10)", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 5. reversal+capex pure-play, group_neutralize within pp too
 ("c16_5_gneut_pp", f"group_neutralize(-{rk(R5,GRP)}+0.5*{rk(INV,GRP)}, {GRP})", {"decay":4,"truncation":0.08,"neutralization":"NONE"}),
 # 6. customer-fade in relationship groups
 ("c16_6_custfade_grp", f"-{rk(CUST,GRP2)}", {"decay":6,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 7. z-score reversion pure-play + capex + value
 ("c16_7_full_pp", f"-{rk(ZC,GRP)}+0.5*{rk(INV,GRP)}+0.3*{rk('divide(ts_backfill(bookvalue_ps,250),close)',GRP)}",
   {"decay":4,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 8. multilayer reversal + capex pure-play
 ("c16_8_ml_capex_pp", f"-ts_rank({rk(R5,GRP)},10)+0.5*{rk(INV,GRP)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 9. z-score rev pure-play, volume-gated
 ("c16_9_zpp_volgate", f"sig=-{rk(ZC,GRP)};\ngate=ts_rank(volume,20)>0.85;\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 10. multilayer z + capex + value pure-play, MARKET neut
 ("c16_10_ml_full_mkt", f"-ts_rank({rk(ZC,GRP)},10)+0.5*{rk(INV,GRP)}+0.3*{rk(CUST,GRP2)}",
   {"decay":4,"truncation":0.12,"neutralization":"MARKET"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_CUSTOMGROUP.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== c16 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 CUSTOMGROUP (bar 2.0/1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
