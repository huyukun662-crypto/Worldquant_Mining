"""D0 round 17: analyst dispersion + revision skew (low-turnover).

Diether-Malloy-Scherbina dispersion anomaly: high analyst disagreement
-> underperforms. Revision skew (#up - #down estimates) -> drift.
Both update slowly -> LOW turnover -> helps FIT (the key bottleneck).
analyst4 consensus components. delay=0, no options.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
def bf(f): return f"ts_backfill(vec_avg({f}),120)"
HI="anl4_basicconqf_high"; LO="anl4_basicconqf_low"; MN="anl4_basicconqf_mean"
PU="anl4_basicconqf_pu"; DN="anl4_basicconqf_down"; NE="anl4_basicconqf_numest"
DISP=f"divide({bf(HI)}-{bf(LO)}, abs({bf(MN)})+0.01)"          # dispersion
SKEW=f"divide({bf(PU)}-{bf(DN)}, {bf(NE)}+1)"                  # revision skew
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
ZC="ts_zscore(close,20)"
C=[
 # 1. dispersion anomaly (high disagreement -> short -> negate)
 ("d17_1_dispersion", f"-{rk(DISP)}", {"decay":8,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 2. revision skew (more up-revisions -> long)
 ("d17_2_revskew", f"{rk(SKEW)}", {"decay":8,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 3. dispersion + revision skew combo
 ("d17_3_disp_skew", f"-{rk(DISP)}+{rk(SKEW)}", {"decay":8,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 4. dispersion + capex quality
 ("d17_4_disp_capex", f"-{rk(DISP)}+0.5*{rk(INV)}", {"decay":8,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 5. coverage momentum (rising analyst count -> attention)
 ("d17_5_coverage", f"{rk(f'ts_delta({bf(NE)},60)')}", {"decay":8,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 6. revision skew + dispersion + capex (3-way low-TO)
 ("d17_6_three", f"-{rk(DISP)}+{rk(SKEW)}+0.5*{rk(INV)}", {"decay":8,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 7. dispersion + revision skew, MARKET neut high trunc (FIT)
 ("d17_7_disp_skew_mkt", f"-{rk(DISP,'subindustry')}+{rk(SKEW,'subindustry')}", {"decay":8,"truncation":0.12,"neutralization":"MARKET"}),
 # 8. revision skew + own mean-reversion (slow + fast)
 ("d17_8_skew_zrev", f"{rk(SKEW)}-0.5*{rk(ZC)}", {"decay":6,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 9. revision skew amplified
 ("d17_9_skew_amp", f"signed_power({rk(SKEW)}-0.5,3)", {"decay":8,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 10. 3-way MARKET neut high trunc
 ("d17_10_three_mkt", f"-{rk(DISP,'subindustry')}+{rk(SKEW,'subindustry')}+0.5*{rk(INV,'subindustry')}", {"decay":8,"truncation":0.12,"neutralization":"MARKET"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_DISPERSION.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== d17 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 DISPERSION (bar 2.0/1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<20}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:90]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
