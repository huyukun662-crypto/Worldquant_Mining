"""D0 round 13: overnight/intraday decomposition + lottery effects.

Untried strong D0 effects (pv1, non-option):
  overnight gap reversal: (open - prev_close)/prev_close reverses
  intraday momentum:      (close - open)/open continues
  lottery/MAX:            extreme max daily return underperforms
These are orthogonal to close-close reversal -> stacking can push SH.
delay=0, no options.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
ON ="divide(open - ts_delay(close,1), ts_delay(close,1))"   # overnight gap
ID ="divide(close - open, open)"                             # intraday
MAXR="ts_max(returns,20)"                                    # lottery
RET="returns"; R5="ts_sum(returns,5)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
C=[
 # 1. overnight gap reversal
 ("o13_1_overnight_rev", f"-{rk(ON)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 2. intraday momentum
 ("o13_2_intraday_mom", f"{rk(ID)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 3. overnight reversal + intraday momentum (classic decomposition)
 ("o13_3_on_rev_id_mom", f"-{rk(ON)}+{rk(ID)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 4. lottery/MAX reversal
 ("o13_4_lottery", f"-{rk(MAXR)}", {"decay":6,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 5. overnight rev + intraday mom + lottery (3 orthogonal)
 ("o13_5_triple", f"-{rk(ON)}+{rk(ID)}-0.5*{rk(MAXR)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 6. overnight rev + intraday mom + close-close reversal + lottery + capex (5-way)
 ("o13_6_five", f"-{rk(ON)}+{rk(ID)}-0.5*{rk(R5)}-0.5*{rk(MAXR)}+0.3*{rk(INV)}",
   {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 7. overnight reversal MARKET neut (more return->FIT)
 ("o13_7_on_rev_mkt", f"-{rk(ON,'market')}", {"decay":4,"truncation":0.10,"neutralization":"MARKET"}),
 # 8. decomposition + capex, MARKET neut
 ("o13_8_decomp_capex_mkt", f"-{rk(ON,'subindustry')}+{rk(ID,'subindustry')}+0.3*{rk(INV,'subindustry')}",
   {"decay":4,"truncation":0.10,"neutralization":"MARKET"}),
 # 9. overnight rev + intraday, decay8, TOP1000
 ("o13_9_decomp_t1000", f"-{rk(ON)}+{rk(ID)}", {"decay":8,"truncation":0.08,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 # 10. triple amplified
 ("o13_10_triple_amp", f"signed_power(-{rk(ON)}+{rk(ID)}-0.5*{rk(MAXR)},3)",
   {"decay":4,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 11. overnight reversal volume-gated
 ("o13_11_on_volgate", f"sig=-{rk(ON)};\ngate=ts_rank(volume,20)>0.80;\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 12. five-way MARKET neut high trunc
 ("o13_12_five_mkt", f"-{rk(ON,'subindustry')}+{rk(ID,'subindustry')}-0.5*{rk(R5,'subindustry')}-0.5*{rk(MAXR,'subindustry')}+0.3*{rk(INV,'subindustry')}",
   {"decay":4,"truncation":0.10,"neutralization":"MARKET"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_OVERNIGHT.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== o13 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 OVERNIGHT (bar 2.0/1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
