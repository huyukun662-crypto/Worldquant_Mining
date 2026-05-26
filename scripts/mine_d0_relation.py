"""D0 round 15: relationship lead-lag momentum (pv13, genuinely new).

rel_ret_cust/comp/part/all = averaged returns of a company's
customers/competitors/partners/related firms. Customer-momentum
(Cohen-Frazzini 2008) is a strong documented lead-lag anomaly:
when your customers' stocks rise, you rise next.  delay=0, no options.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
CUST="ts_backfill(rel_ret_cust,5)"; COMP="ts_backfill(rel_ret_comp,5)"
PART="ts_backfill(rel_ret_part,5)"; ALLR="ts_backfill(rel_ret_all,5)"
CUST5="ts_sum(ts_backfill(rel_ret_cust,5),5)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
ZC="ts_zscore(close,20)"
C=[
 # 1. customer momentum (follow customers' returns)
 ("r15_1_cust_mom", f"{rk(CUST)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 2. partner momentum
 ("r15_2_part_mom", f"{rk(PART)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 3. all-related momentum
 ("r15_3_all_mom", f"{rk(ALLR)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 4. competitor reversal (compete -> negative spillover)
 ("r15_4_comp_rev", f"-{rk(COMP)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 5. competitor momentum (industry tailwind)
 ("r15_5_comp_mom", f"{rk(COMP)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 6. customer + partner momentum combo
 ("r15_6_cust_part", f"{rk(CUST)}+{rk(PART)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 7. customer 5d-sum momentum (smoother)
 ("r15_7_cust5", f"{rk(CUST5)}", {"decay":6,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 8. customer momentum + own mean-reversion (lead-lag + reversal)
 ("r15_8_cust_zrev", f"{rk(CUST)}-0.5*{rk(ZC)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 9. customer + partner + all (full relationship momentum)
 ("r15_9_full_rel", f"{rk(CUST)}+{rk(PART)}+0.5*{rk(ALLR)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 10. customer momentum + capex quality
 ("r15_10_cust_capex", f"{rk(CUST)}+0.5*{rk(INV)}", {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # 11. customer momentum MARKET neut high trunc (FIT)
 ("r15_11_cust_mkt", f"{rk(CUST,'subindustry')}", {"decay":4,"truncation":0.12,"neutralization":"MARKET"}),
 # 12. full relationship + reversal + capex (ensemble)
 ("r15_12_ensemble", f"{rk(CUST)}+{rk(PART)}-0.5*{rk(ZC)}+0.3*{rk(INV)}", {"decay":4,"truncation":0.10,"neutralization":"SUBINDUSTRY"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_RELATION.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== r15 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 RELATION (bar 2.0/1.3): {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<20}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
