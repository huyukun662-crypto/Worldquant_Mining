"""D0 round 6: analyst estimate-revision momentum (strong anomaly).

When analysts revise consensus estimates UP, the stock drifts up
(estimate-revision / PEAD-adjacent anomaly -- among the most robust
in the literature).  Uses analyst4 consensus estimate fields
(delay=0, MATRIX): est_epsa, est_netprofit, est_ebit, est_ebitda,
est_fcf, est_sales, est_tot_assets.

Revision = ts_delta(estimate, window).  Rising = long.
delay=0, cold fields (analyst4), NO options, cold operators
(group_rank, ts_delta, ts_av_diff, group_zscore, hump).
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def bf(f,d=120): return f"ts_backfill({f},{d})"
def rev(f,w): return f"ts_delta({bf(f)},{w})"   # revision over w days
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
INV="divide(ts_backfill(capex,250), ts_backfill(assets,250))"
C=[
 # single-metric EPS revision, various windows
 ("e6_1_eps_rev60", rk(rev("est_epsa",60)), {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("e6_2_eps_rev120", rk(rev("est_epsa",120)), {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("e6_3_netprofit_rev120", rk(rev("est_netprofit",120)), {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("e6_4_ebitda_rev60", rk(rev("est_ebitda",60)), {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # multi-metric revision composite (EPS + netprofit + ebitda)
 ("e6_5_multi_rev", f"{rk(rev('est_epsa',60))}+{rk(rev('est_netprofit',120))}+{rk(rev('est_ebitda',60))}",
   {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # revision via ts_av_diff (vs trailing avg -- smoother)
 ("e6_6_eps_avdiff", rk(f"ts_av_diff({bf('est_epsa')},120)"), {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # EPS revision TOP500
 ("e6_7_eps_rev60_t500", rk(rev("est_epsa",60)), {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # multi-rev TOP500
 ("e6_8_multi_t500", f"{rk(rev('est_epsa',60))}+{rk(rev('est_netprofit',120))}+{rk(rev('est_ebitda',60))}",
   {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # est revision + capex (orthogonal: estimate momentum + investment)
 ("e6_9_rev_capex", f"{rk(rev('est_epsa',60))}+{rk(INV)}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # fcf estimate revision
 ("e6_10_fcf_rev120", rk(rev("est_fcf",120)), {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # multi-rev + hump (low TO)
 ("e6_11_multi_hump", f"hump({rk(rev('est_epsa',60))}+{rk(rev('est_netprofit',120))}+{rk(rev('est_ebitda',60))},hump=0.02)",
   {"decay":6,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # ebit revision TOP500
 ("e6_12_ebit_rev60_t500", rk(rev("est_ebit",60)), {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_ESTREV.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== e6 [{i}/{len(C)}] {fam} ===")
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
    print(f"D0 est-rev: {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    print(f"{'#':<3}{'family':<24}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT':<11} alpha")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<24}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
