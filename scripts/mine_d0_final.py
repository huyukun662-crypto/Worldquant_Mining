"""D0 round 9: GATED (reversal + capex) -- combine the breakthrough.

Findings:
  reversal (news_prev_day_ret)      SH 0.95, TO 0.46, FIT 0.32
  capex/assets                      SH 0.86, TO 0.01
  reversal + capex (v7.6)           SH 1.19, TO 0.40, FIT 0.44  <-- best
  -> need FIT>1.0: gate to cut turnover (fewer trades on news days)

This round gates the reversal+capex composite on extreme-news days
with various thresholds/weights to clear SH>1.25 AND FIT>1.0.
delay=0, cold fields (news12 + fundamental6 capex), NO options.
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
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
G80="gate = ts_rank(abs(ts_backfill(news_pct_30min,5)),60) > 0.80;"
G90="gate = ts_rank(abs(ts_backfill(news_pct_30min,5)),60) > 0.90;"
G95="gate = ts_rank(abs(ts_backfill(news_pct_30min,5)),60) > 0.95;"
def combo(wc): return f"-{rk(PDR)}+{wc}*{rk(INV)}"
C=[
 # gated reversal+capex, various gate thresholds (raise to cut TO)
 ("x9_1_g80_w05", f"sig = {combo('0.5')};\n{G80}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("x9_2_g90_w05", f"sig = {combo('0.5')};\n{G90}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("x9_3_g95_w05", f"sig = {combo('0.5')};\n{G95}\ntrade_when(gate, sig, -1)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # gated + decay smoothing to cut TO further
 ("x9_4_g90_dec", f"sig = {combo('0.5')};\n{G90}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("x9_5_g95_dec", f"sig = {combo('0.5')};\n{G95}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # heavier capex weight (more low-TO component)
 ("x9_6_g90_w10", f"sig = {combo('1.0')};\n{G90}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("x9_7_g95_w10", f"sig = {combo('1.0')};\n{G95}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # decay smoothing window 10
 ("x9_8_g95_dec10", f"sig = {combo('0.5')};\n{G95}\ntrade_when(gate, ts_decay_linear(sig,10), -1)",
   {"decay":12,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # higher decay setting (cut TO)
 ("x9_9_g90_decay20", f"sig = {combo('0.5')};\n{G90}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":20,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # truncation 0.02 tighter
 ("x9_10_g95_t02", f"sig = {combo('0.5')};\n{G95}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":8,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # INDUSTRY neut
 ("x9_11_g95_ind", f"sig = -{rk(PDR,'industry')}+0.5*{rk(INV,'industry')};\n{G95}\ntrade_when(gate, ts_decay_linear(sig,5), -1)",
   {"decay":8,"truncation":0.05,"neutralization":"INDUSTRY"}),
 # heavy capex weight 1.5 + g95 (most low-TO)
 ("x9_12_g95_w15", f"sig = {combo('1.5')};\n{G95}\ntrade_when(gate, ts_decay_linear(sig,10), -1)",
   {"decay":12,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_FINAL.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== x9 [{i}/{len(C)}] {fam} ===")
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
                        and r.sharpe>1.25 and r.fitness>=1.0)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D0 FINAL gated rev+capex: {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    print(f"{'#':<3}{'family':<18}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT':<11} alpha")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<18}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
