"""D0 round 11: price-volume signals (cold constraint relaxed).

Target the D0 bar: SH>2.0, FIT>1.3.  Cold fundamentals capped ~1.2;
pv reversal/momentum are much stronger.  NO options.

Classic high-SH D0 patterns: short-term reversal, VWAP reversal,
volume-scaled reversal, volume-gated reversal, +/- fundamental
quality overlay.  ts_decay_linear + decay manage turnover for FIT.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
RET="returns"
R5="ts_sum(returns,5)"
VWAPDEV="divide(close-vwap,vwap)"
VOLSPK="ts_rank(volume,20) > 0.90"        # volume spike gate
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
C=[
 # 1. basic 1d reversal, decayed
 ("p11_1_rev1", f"-{rk(RET)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 2. 5d reversal
 ("p11_2_rev5", f"-{rk(R5)}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 3. vwap-deviation reversal
 ("p11_3_vwaprev", f"-{rk(VWAPDEV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 4. volume-gated 1d reversal (overreaction on high volume)
 ("p11_4_volgate_rev", f"sig=-{rk(RET)};\ngate={VOLSPK};\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 5. liquidity-scaled reversal (returns per dollar volume)
 ("p11_5_liqrev", f"-{rk('divide(returns, ts_mean(volume,20))')}",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 6. reversal + capex quality overlay
 ("p11_6_rev_capex", f"-{rk(RET)}+0.5*{rk(INV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 7. vwap reversal volume-gated
 ("p11_7_vwap_volgate", f"sig=-{rk(VWAPDEV)};\ngate={VOLSPK};\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 8. 5d reversal volume-gated
 ("p11_8_rev5_volgate", f"sig=-{rk(R5)};\ngate={VOLSPK};\ntrade_when(gate, sig, -1)",
   {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 9. amplified vwap reversal (signed_power bounded)
 ("p11_9_vwap_amp", f"signed_power(-{rk(VWAPDEV)}+0.0,3)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 10. reversal scaled by high-low range (volatility-normalized)
 ("p11_10_range_rev", f"-{rk('divide(returns, divide(high-low,close))')}",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 11. 1d reversal TOP1000 decay8
 ("p11_11_rev1_t1000", f"-{rk(RET)}", {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 # 12. vwap reversal + capex, volume-gated
 ("p11_12_vwap_capex_gate", f"sig=-{rk(VWAPDEV)}+0.5*{rk(INV)};\ngate={VOLSPK};\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_PV.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== p11 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 PV (bar SH>2.0,FIT>1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    print(f"{'#':<3}{'family':<22}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT':<11} alpha")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
