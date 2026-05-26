"""D0 round 5: CLEAN rank-based composites (no z-score cubing).

Evidence:
  group_rank(capex/assets)        = +0.85 SH (clean, f6.5 negated)
  signed_power(z-score, 3)        = destroyed it (-0.04..0.16)
So: build BOUNDED rank composites, hold continuously, combine
orthogonal fundamentals additively. signed_power applied only to
the bounded (rank-0.5) in (-0.5,0.5) where cubing is gentle.

delay=0, cold fields (fundamental6), NO options, NO news gate.
Cold operators: group_rank, signed_power(bounded), hump, ts_av_diff.
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
SG  = "ts_backfill(sales_growth,250)"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
C = [
 # clean raw capex (reproduce the +0.85 baseline)
 ("r5_1_capex_raw", f"{rk(INV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # capex + GP additive rank
 ("r5_2_capex_gp", f"{rk(INV)}+{rk(GP)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # capex + GP + value
 ("r5_3_capex_gp_val", f"{rk(INV)}+{rk(GP)}+{rk(BV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # capex + GP + ROA + CFO + value (5-factor)
 ("r5_4_five_factor", f"{rk(INV)}+{rk(GP)}+{rk(ROA)}+{rk(CFO)}+{rk(BV)}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # capex raw TOP500
 ("r5_5_capex_t500", f"{rk(INV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # capex+GP TOP500
 ("r5_6_capex_gp_t500", f"{rk(INV)}+{rk(GP)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # 5-factor TOP500
 ("r5_7_five_t500", f"{rk(INV)}+{rk(GP)}+{rk(ROA)}+{rk(CFO)}+{rk(BV)}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # bounded signed_power amplification (rank-0.5)^3
 ("r5_8_capex_bamp3", f"signed_power({rk(INV)}-0.5,3)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # capex+GP+sales_growth
 ("r5_9_capex_gp_sg", f"{rk(INV)}+{rk(GP)}+{rk(SG)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # capex+GP hump (low TO)
 ("r5_10_capex_gp_hump", f"hump({rk(INV)}+{rk(GP)},hump=0.02)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # 5-factor TOP200
 ("r5_11_five_t200", f"{rk(INV)}+{rk(GP)}+{rk(ROA)}+{rk(CFO)}+{rk(BV)}", {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP200"}),
 # capex+GP INDUSTRY neut
 ("r5_12_capex_gp_ind", f"{rk(INV,'industry')}+{rk(GP,'industry')}", {"decay":4,"truncation":0.05,"neutralization":"INDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_RANK.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== r5 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr}")
        r=submit(cm.session,fam,expr,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} {r.alpha_id}")
        else: log.warning(f"   FAILED: {r.error[:140]}")
        json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    log.info("=== pass 2 self-corr ===")
    for r in res:
        if not r.ok or not r.alpha_id: continue
        sc,top,stt=fetch_self_corr(cm.session,r.alpha_id,timeout_s=90); r.self_corr=sc
        if top: r.self_corr_peer=top.get("id"); r.self_corr_peer_sharpe=top.get("sharpe")
        log.info(f"   {r.alpha_id} sc={sc} ({stt})")
    json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def ok_(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7)
                        and r.sharpe>1.25 and r.fitness>=1.0 and r.turnover<0.25)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D0 rank round: {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    print(f"{'#':<3}{'family':<22}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT':<11} alpha")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
