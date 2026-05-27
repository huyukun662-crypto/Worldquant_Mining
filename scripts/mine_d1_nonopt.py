"""D1 round 25: NON-OPTION factors at delay=1 vs standard submittable bar
(SH>1.25, TO<0.25, FIT>1.0, self-corr<0.7). NO implied_volatility / option
fields. Pure pv + fundamental, using best learnings (reversal+capex,
z-score mean-reversion, value, fundamental anomalies, news-gate for low TO)."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
R5="ts_sum(returns,5)"; ZC="ts_zscore(close,20)"; ZC10="ts_zscore(close,10)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"     # asset-growth/capex
BV="divide(ts_backfill(bookvalue_ps,250),close)"                 # value
GP="divide(ts_backfill(sales,250)-ts_backfill(cogs,250),ts_backfill(assets,250))"  # gross profitability
ON="divide(open - ts_delay(close,1), ts_delay(close,1))"         # overnight gap (pv1)
NG="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.55);"
C=[
 # 1. classic reversal
 ("d1_1_rev", f"-{rk(R5)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 2. reversal + capex (best D0 performer)
 ("d1_2_rev_capex", f"-{rk(R5)}+0.5*{rk(INV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 3. z-score mean-reversion
 ("d1_3_zrev", f"-{rk(ZC)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 4. z-score + capex + value composite
 ("d1_4_z_capex_val", f"-{rk(ZC)}+0.5*{rk(INV)}+0.3*{rk(BV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 5. reversal + value
 ("d1_5_rev_val", f"-{rk(R5)}+0.4*{rk(BV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 6. gross profitability (quality)
 ("d1_6_gp", f"{rk(GP)}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 7. overnight gap reversal (pv1)
 ("d1_7_overnight_rev", f"-{rk(ON)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 8. reversal news-gated (low TO -> FIT)
 ("d1_8_rev_gated", f"sig=-{rk(R5)};\n{NG}\ntrade_when(gate, sig, -1)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 9. z-score reversal news-gated
 ("d1_9_zrev_gated", f"sig=-{rk(ZC)};\n{NG}\ntrade_when(gate, sig, -1)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 10. composite z+capex+val news-gated
 ("d1_10_combo_gated", f"sig=-{rk(ZC)}+0.5*{rk(INV)}+0.3*{rk(BV)};\n{NG}\ntrade_when(gate, sig, -1)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 11. reversal+capex MARKET neut (return->FIT)
 ("d1_11_rev_capex_mkt", f"-{rk(R5,'subindustry')}+0.5*{rk(INV,'subindustry')}", {"decay":4,"truncation":0.08,"neutralization":"MARKET"}),
 # 12. z-score reversal amplified
 ("d1_12_zrev_amp", f"signed_power(-{rk(ZC)},3)", {"decay":4,"truncation":0.06,"neutralization":"SUBINDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D1_NONOPT.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== d1 [{i}/{len(C)}] {fam} ===")
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
    # standard submittable bar (NOT the D0 2.0 bar)
    def ok_(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7)
                        and r.sharpe>1.25 and r.turnover<0.25 and r.fitness>=1.0)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D1 NON-OPTION (bar SH>1.25 TO<0.25 FIT>1.0 sc<0.7): SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<20}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
