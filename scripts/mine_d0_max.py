"""D0 round 10: maximize SH toward the D0 bar (SH>2.0, FIT>1.3).

D0 submission needs SH>2.0 AND FIT>1.3 (vs 1.25/1.0 for D1) -- a very
high bar for cold non-option signals. Best so far: SH 1.19 (rev+capex).

This round throws the kitchen sink at SH: 4 orthogonal cold sources
(reversal + capex + value + estimate-revision), tight 90th-pct news
gate, signed_power amplification, and HIGHER truncation (0.08-0.12)
to lift returns -> fitness. delay=0, cold fields, NO options.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
PDR="ts_backfill(news_prev_day_ret,5)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
BV ="divide(ts_backfill(bookvalue_ps,250),close)"
REV="ts_delta(ts_backfill(est_epsa,120),60)"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
G90="gate = ts_rank(abs(ts_backfill(news_pct_30min,5)),60) > 0.90;"
# 4-way orthogonal composite (reversal + capex + value + est-revision)
S4=f"-{rk(PDR)}+0.5*{rk(INV)}+0.3*{rk(BV)}+0.3*{rk(REV)}"
S3=f"-{rk(PDR)}+0.5*{rk(INV)}+0.3*{rk(BV)}"
C=[
 # 4-way gated, truncation sweep
 ("m10_1_s4_t08", f"sig={S4};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":6,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 ("m10_2_s4_t10", f"sig={S4};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":6,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 ("m10_3_s4_t12", f"sig={S4};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":6,"truncation":0.12,"neutralization":"SUBINDUSTRY"}),
 # 3-way gated higher trunc
 ("m10_4_s3_t10", f"sig={S3};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":6,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 4-way amplified (bounded signed_power) gated
 ("m10_5_s4_amp", f"sig=signed_power({S4},3);\n{G90}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":6,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 4-way gated, MARKET neut (more return)
 ("m10_6_s4_mkt", f"sig=-{rk(PDR,'market')}+0.5*{rk(INV,'market')}+0.3*{rk(BV,'market')}+0.3*{rk(REV,'market')};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":6,"truncation":0.10,"neutralization":"MARKET"}),
 # 4-way gated NONE neut (max return)
 ("m10_7_s4_none", f"sig=-{rk(PDR,'market')}+0.5*{rk(INV,'market')}+0.3*{rk(BV,'market')}+0.3*{rk(REV,'market')};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":6,"truncation":0.10,"neutralization":"NONE"}),
 # reversal-heavy 4-way (reversal is strongest), higher trunc
 ("m10_8_revheavy", f"sig=-1.5*{rk(PDR)}+0.5*{rk(INV)}+0.3*{rk(BV)};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # reversal-heavy amplified
 ("m10_9_revheavy_amp", f"sig=signed_power(-1.5*{rk(PDR)}+0.5*{rk(INV)}+0.3*{rk(BV)},3);\n{G90}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":4,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 4-way no gate, high trunc (compare gate value)
 ("m10_10_s4_nogate", f"signed_power({S4},3)",
   {"decay":6,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
 # 4-way gated, decay smoothing + trunc 0.08
 ("m10_11_s4_dec", f"sig={S4};\n{G90}\ntrade_when(gate, ts_decay_linear(sig,10), -1)",
   {"decay":12,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # reversal-heavy 4-way + est-rev, trunc 0.12
 ("m10_12_full_t12", f"sig=-1.5*{rk(PDR)}+0.5*{rk(INV)}+0.3*{rk(BV)}+0.3*{rk(REV)};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.12,"neutralization":"SUBINDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_MAX.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== m10 [{i}/{len(C)}] {fam} ===")
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
    # D0 bar: SH>2.0, FIT>1.3
    def ok_(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7)
                        and r.sharpe>2.0 and r.fitness>=1.3)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D0 MAX (bar SH>2.0,FIT>1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    print(f"{'#':<3}{'family':<18}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT':<11} alpha")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<18}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
