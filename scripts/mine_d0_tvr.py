"""D0 round 18: turnover-targeting operators (last untried lever).

ts_target_tvr_decay / ts_target_tvr_delta_limit force a turnover
target while preserving more signal than plain ts_decay_linear.
The FIT bottleneck = high-SH reversals have high TO. These operators
may keep the SH while cutting TO -> lift FIT. delay=0, no options.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
R5="ts_sum(returns,5)"; ZC="ts_zscore(close,20)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
REVCAP=f"-{rk(R5)}+0.5*{rk(INV)}"   # the SH=1.19 base
ZREV=f"-{rk(ZC)}"
C=[
 # 1. reversal+capex with target-tvr decay (target low TO)
 ("t18_1_revcap_ttd", f"ts_target_tvr_decay({REVCAP}, tvr=0.1)", {"decay":0,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 ("t18_2_revcap_ttd15", f"ts_target_tvr_decay({REVCAP}, tvr=0.15)", {"decay":0,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 3. z-reversal with target-tvr
 ("t18_3_zrev_ttd", f"ts_target_tvr_decay({ZREV}, tvr=0.1)", {"decay":0,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 4. reversal+capex with delta-limit
 ("t18_4_revcap_dl", f"ts_target_tvr_delta_limit({REVCAP}, tvr=0.1)", {"decay":0,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 5. z-reversal delta-limit
 ("t18_5_zrev_dl", f"ts_target_tvr_delta_limit({ZREV}, tvr=0.12)", {"decay":0,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 6. reversal+capex target-tvr, MARKET neut high trunc (FIT)
 ("t18_6_revcap_ttd_mkt", f"ts_target_tvr_decay({REVCAP}, tvr=0.12)", {"decay":0,"truncation":0.12,"neutralization":"MARKET"}),
 # 7. pure reversal target-tvr (highest raw SH 0.95)
 ("t18_7_rev_ttd", f"ts_target_tvr_decay(-{rk(R5)}, tvr=0.1)", {"decay":0,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 8. z-reversal+capex target-tvr
 ("t18_8_zcap_ttd", f"ts_target_tvr_decay(-{rk(ZC)}+0.5*{rk(INV)}, tvr=0.1)", {"decay":0,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_TVR.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== t18 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr.replace(chr(10),' | ')}")
        r=submit(cm.session,fam,expr,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} {r.alpha_id}")
        else: log.warning(f"   FAILED: {r.error[:150]}")
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
    print(f"D0 TVR (bar 2.0/1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:90]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
