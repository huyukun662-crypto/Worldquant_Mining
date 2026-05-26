"""D0 round 12: idiosyncratic/residual reversal + high-FIT tuning.

Best D0 so far ~SH 1.24 / FIT 0.8 vs bar 2.0/1.3. Try residual
reversal (remove common factors -> stronger stock-specific reversal)
via regression_neut/vector_neut, plus less neutralization + higher
truncation to lift returns->fitness. delay=0, no options.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
RET="returns"; R5="ts_sum(returns,5)"
VWAPDEV="divide(close-vwap,vwap)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
VOLSPK="ts_rank(volume,20) > 0.85"
C=[
 # residual reversal: remove market via group_zscore(returns, market) then reverse
 ("q12_1_resid_mkt", f"-group_zscore({RET},market)", {"decay":4,"truncation":0.08,"neutralization":"MARKET"}),
 # residual reversal subindustry-demeaned, higher trunc, MARKET neut for return
 ("q12_2_resid_subind", f"-group_zscore({RET},subindustry)", {"decay":4,"truncation":0.10,"neutralization":"MARKET"}),
 # vector_neut returns against market cap (size-neutral reversal)
 ("q12_3_5d_resid", f"-group_zscore({R5},subindustry)", {"decay":6,"truncation":0.10,"neutralization":"MARKET"}),
 # idiosyncratic reversal: returns minus sector mean, gated by vol spike
 ("q12_4_resid_gate", f"sig=-group_zscore({RET},subindustry);\ngate={VOLSPK};\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.10,"neutralization":"MARKET"}),
 # vwap residual reversal + capex, NONE neut (max return->FIT)
 ("q12_5_vwap_resid_none", f"-{rk(VWAPDEV,'subindustry')}+0.5*{rk(INV,'subindustry')}",
   {"decay":4,"truncation":0.10,"neutralization":"NONE"}),
 # residual reversal high trunc 0.15
 ("q12_6_resid_t15", f"-group_zscore({RET},subindustry)", {"decay":4,"truncation":0.15,"neutralization":"MARKET"}),
 # 5d residual reversal gated + decay
 ("q12_7_5d_resid_gate", f"sig=-group_zscore({R5},subindustry);\ngate={VOLSPK};\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":6,"truncation":0.10,"neutralization":"MARKET"}),
 # residual reversal amplified, SECTOR neut
 ("q12_8_resid_amp", f"signed_power(-group_zscore({RET},subindustry),3)", {"decay":4,"truncation":0.10,"neutralization":"SECTOR"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_RESID.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== q12 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 RESID (bar 2.0/1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
