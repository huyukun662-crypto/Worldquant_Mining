"""D1 round 28: DIVERSE non-option signal cores for an uncorrelated basket.
Existing 6 submittable are all the same z-score-reversal+quality composite
(mutually correlated). Mine genuinely different cores: profitability
(ROE/ROA), earnings-quality (accruals), cash profitability, leverage,
low-vol, momentum, investment/asset-growth, value. All pure pv+fundamental
(NO implied_volatility / option). Low-TO (backfilled fundamentals + decay).
delay=1. Bar SH>1.25 TO<0.25 FIT>1.0 sc<0.7."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def bf(f,n=250): return f"ts_backfill({f},{n})"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
EBIT=bf("ebit"); EQ=bf("equity"); ASST=bf("assets"); CFO=bf("cashflow_op")
DEBT=bf("debt"); SALES=bf("sales"); COGS=bf("cogs"); BV=bf("bookvalue_ps")
ROE=f"divide({EBIT},{EQ})"; ROA=f"divide({EBIT},{ASST})"
ACCR=f"divide({EBIT}-{CFO},{ASST})"          # accruals (low good)
CFOA=f"divide({CFO},{ASST})"                 # cash profitability
LEV=f"divide({DEBT},{EQ})"                    # leverage (low good)
GP=f"divide({SALES}-{COGS},{ASST})"          # gross profitability
VAL=f"divide({BV},close)"                     # book/price value
VOL=f"ts_std_dev(returns,60)"                 # volatility (low-vol anomaly)
MOM=f"ts_sum(returns,230)-ts_sum(returns,20)" # 12-1 momentum
AG=f"divide(ts_delta({ASST},250),{ASST})"     # asset growth (low good)
def C():
 D={"decay":12,"truncation":0.08,"neutralization":"MARKET"}
 S={"decay":12,"truncation":0.05,"neutralization":"SUBINDUSTRY"}
 return [
 ("f28_1_roe",         f"{rk(ROE)}", dict(D)),
 ("f28_2_roa",         f"{rk(ROA)}", dict(D)),
 ("f28_3_accruals",    f"-{rk(ACCR)}", dict(D)),
 ("f28_4_cfo_assets",  f"{rk(CFOA)}", dict(D)),
 ("f28_5_low_lev",     f"-{rk(LEV)}", dict(D)),
 ("f28_6_low_vol",     f"-{rk(VOL)}", dict(S)),
 ("f28_7_mom_12_1",    f"{rk(MOM)}", dict(S)),
 ("f28_8_asset_growth",f"-{rk(AG)}", dict(D)),
 # pure-fundamental quality composite (NO reversal anchor -> orthogonal to existing)
 ("f28_9_qual_combo",  f"{rk(ROE)}+{rk(CFOA)}-0.5*{rk(ACCR)}", dict(D)),
 ("f28_10_grossprofit",f"{rk(GP)}", dict(D)),
 # value + quality (different mix than existing)
 ("f28_11_val_qual",   f"{rk(VAL)}+{rk(ROA)}", dict(D)),
 # low-vol + value + quality defensive composite
 ("f28_12_defensive",  f"-0.5*{rk(VOL)}+0.5*{rk(VAL)}+{rk(ROA)}", dict(D)),
 ]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D1_DIVERSE.json"; res=[]; cands=C()
    for i,(fam,expr,st) in enumerate(cands,1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== f28 [{i}/{len(cands)}] {fam} ({s['neutralization']}) ===")
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
    ok=sorted([r for r in res if r.ok],key=lambda r:r.fitness,reverse=True)
    print("\n"+"="*120)
    print(f"D1 DIVERSE NON-OPTION (bar SH>1.25 TO<0.25 FIT>1.0 sc<0.7): SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
