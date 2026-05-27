"""D0 round 30: the WINNING non-option quality composite, tuned at delay=0.
Earlier D0 non-option exhaustion (cap SH 1.24) predated this recipe -- it
used reversal-only. The quality composite (z-score reversal + capex +
value + gross-profitability, MARKET neut, decay, signed_power amp) broke
FIT>1.0 at D1; D0 signals are stronger (no 1-day lag) so worth a param
sweep. Pure pv+fundamental, NO option fields. delay=0."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def bf(f,n=250): return f"ts_backfill({f},{n})"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
Z="ts_zscore(close,20)"
INV=f"divide({bf('capex')},{bf('assets')})"
VAL=f"divide({bf('bookvalue_ps')},close)"
GP=f"divide({bf('sales')}-{bf('cogs')},{bf('assets')})"
def base(wz=1.0,wi=0.5,wb=0.3,wg=0.5,g="subindustry"):
    return f"-{wz}*{rk(Z,g)}+{wi}*{rk(INV,g)}+{wb}*{rk(VAL,g)}+{wg}*{rk(GP,g)}"
def C():
 return [
 ("h30_1_sub_d4_t05",   base(), {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("h30_2_mkt_d4_t08",   base(g="subindustry"), {"decay":4,"truncation":0.08,"neutralization":"MARKET"}),
 ("h30_3_mkt_d8_t10",   base(g="subindustry"), {"decay":8,"truncation":0.10,"neutralization":"MARKET"}),
 # the exact D1-winner config, at D0
 ("h30_4_amp_mkt_d12",  f"signed_power({base(g='subindustry')},3)", {"decay":12,"truncation":0.10,"neutralization":"MARKET"}),
 ("h30_5_amp_sub_d4",   f"signed_power({base()},3)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("h30_6_sub_t1000",    base(), {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY","universe":"TOP1000"}),
 # quality-heavy
 ("h30_7_qheavy_amp",   f"signed_power({base(wi=0.5,wb=0.5,wg=0.5,g='subindustry')},3)", {"decay":8,"truncation":0.08,"neutralization":"MARKET"}),
 ("h30_8_ind_d6",       base(g="subindustry"), {"decay":6,"truncation":0.06,"neutralization":"INDUSTRY"}),
 ("h30_9_amp_mkt_d8",   f"signed_power({base(g='subindustry')},3)", {"decay":8,"truncation":0.08,"neutralization":"MARKET"}),
 # stronger reversal weight
 ("h30_10_revheavy",    base(wz=1.5,g="subindustry"), {"decay":8,"truncation":0.08,"neutralization":"MARKET"}),
 ("h30_11_sub_d2_t04",  base(), {"decay":2,"truncation":0.04,"neutralization":"SUBINDUSTRY"}),
 ("h30_12_qheavy_sub",  f"signed_power({base(wi=0.5,wb=0.5,wg=0.5)},3)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_QUALITY.json"; res=[]; cands=C()
    for i,(fam,expr,st) in enumerate(cands,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== h30 [{i}/{len(cands)}] {fam} ({s['neutralization']} d{s['decay']} t{s['truncation']}) ===")
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
    # report both standard bar and D0-submittable bar
    def std(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7)
                        and r.sharpe>1.25 and r.turnover<0.25 and r.fitness>=1.0)
    def d0bar(r): return std(r) and r.sharpe>2.0 and r.fitness>=1.3
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120)
    print(f"D0 QUALITY NON-OPTION: std-bar(SH>1.25/FIT>1.0)={sum(1 for r in ok if std(r))}  D0-bar(SH>2.0/FIT>1.3)={sum(1 for r in ok if d0bar(r))}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        tag="*** D0-SUBMIT ***" if d0bar(r) else ("std-ok" if std(r) else "no")
        print(f"{i:<3}{r.family:<20}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {tag:<16} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
