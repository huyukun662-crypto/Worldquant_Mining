"""D0 round 8: GATED short-term reversal.

Reversal has the best SH (0.95) but high turnover (0.45) -> low
fitness. The news-activity gate (which HURT slow fundamentals) should
HELP fast reversal: fire only on extreme-news overreaction days ->
fewer trades -> low TO -> high FIT.  This is the IV+news structure
that previously hit FIT~2.5.

delay=0, cold fields (news12 reaction + news_pct gate), NO options.
Cold ops: group_rank, trade_when, ts_decay_linear, signed_power.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
PDR="ts_backfill(news_prev_day_ret,5)"
UP ="ts_backfill(news_max_up_ret,5)"; DN="ts_backfill(news_max_dn_ret,5)"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
# news activity gate (cold news_pct fields, delay=0)
G80="gate = ts_rank(abs(ts_backfill(news_pct_30min,5)),60) > 0.80;"
G90="gate = ts_rank(abs(ts_backfill(news_pct_30min,5)),60) > 0.90;"
C=[
 # gated reversal, 80th pct news gate
 ("w8_1_grev80", f"sig = -{rk(PDR)};\n{G80}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated reversal, 90th pct (rarer -> lower TO)
 ("w8_2_grev90", f"sig = -{rk(PDR)};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated reversal + decay smoothing
 ("w8_3_grev90_dec", f"sig = -{rk(PDR)};\n{G90}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated bigmove reversal
 ("w8_4_gbig90", f"sig = -{rk(f'{UP}+{DN}')};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated reversal amplified (signed_power on bounded rank)
 ("w8_5_grev90_amp", f"sig = signed_power(-{rk(PDR)}+0.5-0.5,3);\n{G90}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated reversal TOP1000
 ("w8_6_grev90_t1000", f"sig = -{rk(PDR)};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 # gated reversal 80th, decay8
 ("w8_7_grev80_dec8", f"sig = -{rk(PDR)};\n{G80}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated net-move reversal 90
 ("w8_8_gnet90", f"sig = -{rk(f'{UP}-{DN}')};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated reversal INDUSTRY
 ("w8_9_grev90_ind", f"sig = -{rk(PDR,'industry')};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"INDUSTRY"}),
 # gated reversal 90 + capex overlay
 ("w8_10_grev_capex", f"sig = -{rk(PDR)}+0.5*{rk('divide(ts_backfill(capex,250),ts_backfill(assets,250))')};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated reversal 90 MARKET neut
 ("w8_11_grev90_mkt", f"sig = -{rk(PDR,'market')};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"MARKET"}),
 # gated reversal amp5 90
 ("w8_12_grev90_amp5", f"sig = signed_power(-{rk(PDR)}+0.0,5);\n{G90}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_GATEDREV.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== w8 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr.replace(chr(10),' | ')}")
        r=submit(cm.session,fam,expr,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} {r.alpha_id}")
        else: log.warning(f"   FAILED: {r.error[:140]}")
        json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    log.info("=== pass2 self-corr ===")
    for r in res:
        if not r.ok or not r.alpha_id: continue
        sc,top,stt=fetch_self_corr(cm.session,r.alpha_id,timeout_s=90); r.self_corr=sc
        if top: r.self_corr_peer=top.get("id"); r.self_corr_peer_sharpe=top.get("sharpe")
        log.info(f"   {r.alpha_id} sc={sc} ({stt})")
    json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def ok_(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7)
                        and r.sharpe>1.25 and r.fitness>=1.0)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D0 gated-reversal: {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    print(f"{'#':<3}{'family':<20}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT':<11} alpha")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<20}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
