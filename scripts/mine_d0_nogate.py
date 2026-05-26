"""D0 round 4: NON-gated amplification of the strongest fundamental
signals. The news gate destroyed slow fundamental signals (g3.1
capex: 0.85 un-gated -> 0.16 gated). Instead amplify cross-sectionally
and hold continuously, across tighter universes.

Strongest base: capex/assets (+0.85), gross profit (+0.44).
All delay=0, cold fields (fundamental6), NO options, NO gate.
Cold operators: group_zscore, group_rank, signed_power, hump, ts_av_diff.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)

GP  = "divide(ts_backfill(revenue,250)-ts_backfill(cogs,250), ts_backfill(assets,250))"
INV = "divide(ts_backfill(capex,250), ts_backfill(assets,250))"
ROA = "ts_backfill(return_assets,250)"
CFO = "divide(ts_backfill(cashflow_op,250), ts_backfill(assets,250))"
BV  = "divide(ts_backfill(bookvalue_ps,250), close)"

C = [
 # capex(+) amplified, no gate, various universes
 ("n4_1_capex_amp3_t3k", f"signed_power(group_zscore({INV},subindustry),3)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("n4_2_capex_amp3_t500", f"signed_power(group_zscore({INV},subindustry),3)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 ("n4_3_capex_amp3_t200", f"signed_power(group_zscore({INV},subindustry),3)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP200"}),
 # capex+GP composite amplified
 ("n4_4_capex_gp_amp3", f"signed_power(group_zscore({INV},subindustry)+group_zscore({GP},subindustry),3)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("n4_5_capex_gp_amp3_t500", f"signed_power(group_zscore({INV},subindustry)+group_zscore({GP},subindustry),3)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # capex + GP + value triple
 ("n4_6_triple_amp3", f"signed_power(group_zscore({INV},subindustry)+group_zscore({GP},subindustry)+0.5*group_zscore({BV},subindustry),3)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("n4_7_triple_amp3_t500", f"signed_power(group_zscore({INV},subindustry)+group_zscore({GP},subindustry)+0.5*group_zscore({BV},subindustry),3)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # full quality+capex
 ("n4_8_quality_capex", f"signed_power(group_zscore({GP},subindustry)+group_zscore({ROA},subindustry)+group_zscore({CFO},subindustry)+group_zscore({INV},subindustry),3)",
   {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("n4_9_quality_capex_t500", f"signed_power(group_zscore({GP},subindustry)+group_zscore({ROA},subindustry)+group_zscore({CFO},subindustry)+group_zscore({INV},subindustry),3)",
   {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # capex amp5 (stronger amplification)
 ("n4_10_capex_amp5_t500", f"signed_power(group_zscore({INV},subindustry),5)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # capex INDUSTRY neut
 ("n4_11_capex_industry", f"signed_power(group_zscore({INV},industry),3)",
   {"decay":4,"truncation":0.05,"neutralization":"INDUSTRY"}),
 # capex+GP amp5 TOP200
 ("n4_12_capex_gp_amp5_t200", f"signed_power(group_zscore({INV},subindustry)+group_zscore({GP},subindustry),5)",
   {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP200"}),
]

def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth as {cm.credentials.username}")
    out=REPO/"WQ_D0_NOGATE.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== n4 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr}")
        r=submit(cm.session,fam,expr,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} {r.alpha_id}")
        else: log.warning(f"   FAILED: {r.error[:140]}")
        json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    log.info("=== pass 2: self-corr ===")
    for r in res:
        if not r.ok or not r.alpha_id: continue
        sc,top,stt=fetch_self_corr(cm.session,r.alpha_id,timeout_s=90); r.self_corr=sc
        if top: r.self_corr_peer=top.get("id"); r.self_corr_peer_sharpe=top.get("sharpe")
        log.info(f"   {r.alpha_id} sc={sc} ({stt})")
    json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def submok(r):
        return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                and (r.self_corr is None or abs(r.self_corr)<0.7)
                and r.sharpe>1.25 and r.fitness>=1.0 and r.turnover<0.25)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D0 no-gate: {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if submok(r))}")
    print(f"{'#':<3}{'family':<26}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT':<11} alpha")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<26}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if submok(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0

if __name__=="__main__": sys.exit(main() or 0)
