"""D0 round 20: push the IV60-skew winner (SH 1.88, FIT 2.10) past 2.0.

v19.1 = quantile(iv60_skew) + signed_power(.,3) + news_gate.
FIT already 2.10 (>>1.3). Need +0.12 SH. Tune: gate threshold,
signed_power exponent, decay, truncation, IV term-structure 2nd
signal (orthogonal IV-native). delay=0.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def q(x): return f"quantile({x})"
IV60="ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5)"
TERM="ts_backfill(implied_volatility_call_30 - implied_volatility_call_120, 5)"  # call term structure
G80="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.80);"
G90="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.90);"
G70="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.70);"
def sp(s,p): return f"signed_power({s}-0.5,{p})"
C=[
 # gate threshold sweep (v19.1 base = G80, decay4, p3)
 ("w20_1_g70", f"score={q(IV60)};\n{G70}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 ("w20_2_g90", f"score={q(IV60)};\n{G90}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # signed_power exponent sweep
 ("w20_3_p4", f"score={q(IV60)};\n{G80}\ntrade_when(gate, ts_decay_linear({sp('score',4)},5), -1)", {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 ("w20_4_p2", f"score={q(IV60)};\n{G80}\ntrade_when(gate, ts_decay_linear({sp('score',2)},5), -1)", {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # decay sweep
 ("w20_5_dec2", f"score={q(IV60)};\n{G80}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":2,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 ("w20_6_dec6", f"score={q(IV60)};\n{G80}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":6,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # truncation sweep
 ("w20_7_t01", f"score={q(IV60)};\n{G80}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":4,"truncation":0.01,"neutralization":"SUBINDUSTRY"}),
 ("w20_8_t03", f"score={q(IV60)};\n{G80}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":4,"truncation":0.03,"neutralization":"SUBINDUSTRY"}),
 # IV skew + IV term-structure (orthogonal IV-native 2nd signal)
 ("w20_9_iv_term", f"score={q(IV60)}+0.3*{q(TERM)};\n{G80}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 ("w20_10_iv_term_g90", f"score={q(IV60)}+0.3*{q(TERM)};\n{G90}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # g90 + p4 (tighter + stronger amp)
 ("w20_11_g90_p4", f"score={q(IV60)};\n{G90}\ntrade_when(gate, ts_decay_linear({sp('score',4)},5), -1)", {"decay":4,"truncation":0.02,"neutralization":"SUBINDUSTRY"}),
 # INDUSTRY neut variant
 ("w20_12_industry", f"score={q(IV60)};\n{G80}\ntrade_when(gate, ts_decay_linear({sp('score',3)},5), -1)", {"decay":4,"truncation":0.02,"neutralization":"INDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_IV2.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== w20 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 IV2 (bar 2.0/1.3): {len(ok)}/{len(res)} OK  SUBMITTABLE={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
