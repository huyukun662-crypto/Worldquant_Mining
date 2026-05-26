"""D0 round 19: IV-skew options (the proven SH>2.0 structure) at D0.

Non-option D0 capped at SH 1.24. IV-skew + news-gate + signed_power
hit SH 2.0+/FIT 2.5 at D1; apply at D0 (option8 implied_volatility).
delay=0. Targets the D0 bar SH>2.0, FIT>1.3.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
GATE="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.80);"
IV60="ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5)"
IV30="ts_backfill(implied_volatility_call_30 - implied_volatility_put_30, 5)"
IV90="ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 5)"
IV120="ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5)"
SKEW60="ts_backfill(implied_volatility_mean_skew_60,5)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
def q(x): return f"quantile({x})"
C=[
 # 1. p3 structure: quantile(iv60) + signed_power, news gate
 ("v19_1_iv60_p3", f"score={q(IV60)};\n{GATE}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), -1)",
   {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 2. iv60 + capex (replace short with d0 capex)
 ("v19_2_iv60_capex", f"score={q(IV60)}+0.5*{q(INV)};\n{GATE}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), -1)",
   {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 3. iv30 skew
 ("v19_3_iv30", f"score={q(IV30)};\n{GATE}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), -1)",
   {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 4. iv120 skew + capex
 ("v19_4_iv120_capex", f"score={q(IV120)}+0.5*{q(INV)};\n{GATE}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), -1)",
   {"decay":6,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 5. direct mean_skew field
 ("v19_5_meanskew", f"score={q(SKEW60)};\n{GATE}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), -1)",
   {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 6. iv90 + capex
 ("v19_6_iv90_capex", f"score={q(IV90)}+0.5*{q(INV)};\n{GATE}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), -1)",
   {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 7. iv60 raw rank-sum (no signed_power)
 ("v19_7_iv60_rank", f"score={rk(IV60)};\n{GATE}\ntrade_when(gate, ts_decay_linear(score,5), -1)",
   {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 8. iv60 + capex no gate
 ("v19_8_iv60_capex_nogate", f"signed_power({q(IV60)}+0.5*{q(INV)}-0.5,3)",
   {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 9. iv120 + capex + value
 ("v19_9_iv120_full", f"score={q(IV120)}+0.5*{q(INV)}+0.3*{q('divide(ts_backfill(bookvalue_ps,250),close)')};\n{GATE}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), -1)",
   {"decay":6,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # 10. iv60 amp5
 ("v19_10_iv60_amp5", f"score={q(IV60)};\n{GATE}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,5),5), -1)",
   {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_IV.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== v19 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 IV (bar 2.0/1.3): {len(ok)}/{len(res)} OK  SUBMITTABLE={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<24}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** YES-SUBMIT ***' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
