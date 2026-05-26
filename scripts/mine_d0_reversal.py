"""D0 round 7: short-term reversal (strongest equity micro-effect),
built from cold news-reaction fields + capex quality overlay.

After ~50 fundamental/estimate candidates topped at SH~0.90, switch to
short-term reversal: fade recent winners.  Cold source: news12
news-reaction returns (news_prev_day_ret, news_max_up/dn_ret) at
delay=0 (NO price-volume pv1, NO options).

Reversal has high turnover -> use ts_decay_linear + decay setting to
keep TO < 0.25.  Cold operators: group_rank, ts_decay_linear,
ts_mean, hump, signed_power(bounded).
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr,
                               _load, VENDOR, REPO, log)
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
PDR="ts_backfill(news_prev_day_ret,5)"
UP ="ts_backfill(news_max_up_ret,5)"
DN ="ts_backfill(news_max_dn_ret,5)"
INV="divide(ts_backfill(capex,250), ts_backfill(assets,250))"
C=[
 # pure prev-day-return reversal (fade winners)
 ("v7_1_pdr_rev", f"-{rk(PDR)}", {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("v7_2_pdr_rev_d20", f"-{rk(PDR)}", {"decay":20,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # fade big movers: up+dn magnitude reversal
 ("v7_3_bigmove_rev", f"-{rk(f'{UP}+{DN}')}", {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # net move reversal (up - |dn|)
 ("v7_4_netmove_rev", f"-{rk(f'{UP}-{DN}')}", {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # reversal smoothed over 5d mean
 ("v7_5_pdr_mean5", f"-{rk(f'ts_mean({PDR},5)')}", {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # reversal + capex quality overlay (long cheap-investment losers)
 ("v7_6_rev_capex", f"-{rk(PDR)}+0.5*{rk(INV)}", {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # reversal TOP500
 ("v7_7_pdr_t500", f"-{rk(PDR)}", {"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # reversal TOP1000 decay12
 ("v7_8_pdr_t1000", f"-{rk(PDR)}", {"decay":12,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 # net move reversal decay20
 ("v7_9_netmove_d20", f"-{rk(f'{UP}-{DN}')}", {"decay":20,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # reversal INDUSTRY neut
 ("v7_10_pdr_industry", f"-{rk(PDR,'industry')}", {"decay":8,"truncation":0.05,"neutralization":"INDUSTRY"}),
 # bigmove reversal TOP500 decay12
 ("v7_11_bigmove_t500", f"-{rk(f'{UP}+{DN}')}", {"decay":12,"truncation":0.05,"neutralization":"SUBINDUSTRY","universe":"TOP500"}),
 # reversal MARKET neut
 ("v7_12_pdr_market", f"-{rk(PDR,'market')}", {"decay":8,"truncation":0.05,"neutralization":"MARKET"}),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_REVERSAL.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== v7 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr}")
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
                        and r.sharpe>1.25 and r.fitness>=1.0 and r.turnover<0.25)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D0 reversal: {len(ok)}/{len(res)} OK  submittable={sum(1 for r in ok if ok_(r))}")
    print(f"{'#':<3}{'family':<22}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT':<11} alpha")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'YES-SUBMIT' if ok_(r) else 'no':<11} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
