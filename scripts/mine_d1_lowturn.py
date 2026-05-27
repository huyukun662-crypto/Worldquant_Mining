"""D1 round 26: NON-OPTION, attack the FIT barrier via LOW TURNOVER.
WQ Fitness = SH*sqrt(returns/max(TO,0.125)). Round 25 best (z+capex+val:
SH 1.37, TO 0.25, FIT 0.88) is FIT-limited by turnover. Heavy decay /
longer signal windows cut TO toward 0.125 -> FIT up ~sqrt(2) -> >1.0.
Pure pv+fundamental. delay=1. Bar SH>1.25 TO<0.25 FIT>1.0 sc<0.7."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
ZC="ts_zscore(close,20)"; ZC60="ts_zscore(close,60)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
BV="divide(ts_backfill(bookvalue_ps,250),close)"
GP="divide(ts_backfill(sales,250)-ts_backfill(cogs,250),ts_backfill(assets,250))"
EY="divide(ts_backfill(fn_income,250),close)"   # earnings yield-ish (fallback if invalid)
COMBO=f"-{rk(ZC)}+0.5*{rk(INV)}+0.3*{rk(BV)}"   # round-25 best composite
COMBOQ=f"-{rk(ZC)}+0.5*{rk(INV)}+0.3*{rk(BV)}+0.3*{rk(GP)}"
def C():
 return [
 # round-25 best composite + heavy decay to cut TO
 ("e26_1_combo_dec12", COMBO, {"decay":12,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("e26_2_combo_dec20", COMBO, {"decay":20,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # explicit ts_decay_linear smoothing wrapper
 ("e26_3_combo_tsdecay", f"ts_decay_linear({COMBO},15)", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # slower z-score (60d) -> lower TO base
 ("e26_4_z60_combo", f"-{rk(ZC60)}+0.5*{rk(INV)}+0.3*{rk(BV)}", {"decay":10,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # add gross-profitability quality (low-TO) to lift returns/FIT
 ("e26_5_comboq_dec12", COMBOQ, {"decay":12,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # MARKET neut (spreads weight, often lifts returns->FIT) + decay
 ("e26_6_combo_mkt_dec12", f"-{rk(ZC,'subindustry')}+0.5*{rk(INV,'subindustry')}+0.3*{rk(BV,'subindustry')}", {"decay":12,"truncation":0.08,"neutralization":"MARKET"}),
 # ts_mean smoothing of the z-score component
 ("e26_7_combo_tsmean", f"-{rk('ts_mean(ts_zscore(close,20),10)')}+0.5*{rk(INV)}+0.3*{rk(BV)}", {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # value+quality heavy (inherently low TO), light reversal
 ("e26_8_valqual", f"0.5*{rk(BV)}+0.5*{rk(GP)}+0.3*{rk(INV)}-0.3*{rk(ZC)}", {"decay":12,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # signed_power amplify the composite (concentrate conviction -> returns up)
 ("e26_9_combo_amp", f"signed_power({COMBO},3)", {"decay":12,"truncation":0.06,"neutralization":"SUBINDUSTRY"}),
 # decay20 + market
 ("e26_10_combo_mkt_dec20", f"-{rk(ZC,'subindustry')}+0.5*{rk(INV,'subindustry')}+0.3*{rk(BV,'subindustry')}", {"decay":20,"truncation":0.08,"neutralization":"MARKET"}),
 # comboq market
 ("e26_11_comboq_mkt", f"-{rk(ZC,'subindustry')}+0.5*{rk(INV,'subindustry')}+0.3*{rk(BV,'subindustry')}+0.3*{rk(GP,'subindustry')}", {"decay":12,"truncation":0.08,"neutralization":"MARKET"}),
 # slow z60 + value+quality, market
 ("e26_12_z60valqual_mkt", f"-{rk(ZC60,'subindustry')}+0.5*{rk(BV,'subindustry')}+0.4*{rk(GP,'subindustry')}", {"decay":12,"truncation":0.08,"neutralization":"MARKET"}),
 ]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D1_LOWTURN.json"; res=[]; cands=C()
    for i,(fam,expr,st) in enumerate(cands,1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== e26 [{i}/{len(cands)}] {fam} ===")
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
                        and r.sharpe>1.25 and r.turnover<0.25 and r.fitness>=1.0)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D1 LOW-TURN NON-OPTION (bar SH>1.25 TO<0.25 FIT>1.0 sc<0.7): SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<24}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
