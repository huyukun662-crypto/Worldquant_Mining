"""D1 round 29: quality-anchored composites with DIFFERENT price-reversal
anchors -> submittable AND uncorrelated with the existing z-score(close,20)
family. Round 28 showed pure fundamentals (no price anchor) are too weak
(SH<0.5) at D1; the SH comes from the reversal anchor. Vary the anchor:
zscore60, vwap-deviation, short/long return-reversal, high-low range.
Pure pv+fundamental (NO option). delay=1, MARKET neut, low-TO."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def bf(f,n=250): return f"ts_backfill({f},{n})"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
INV=f"divide({bf('capex')},{bf('assets')})"
VAL=f"divide({bf('bookvalue_ps')},close)"
GP=f"divide({bf('sales')}-{bf('cogs')},{bf('assets')})"
QUAL=f"+0.5*{rk(INV)}+0.3*{rk(VAL)}+0.5*{rk(GP)}"   # same quality block as winner
# DIFFERENT reversal anchors (each orthogonal-ish to zscore(close,20)):
A={
 "z60":   "ts_zscore(close,60)",
 "vwapdev":"divide(close-vwap,vwap)",
 "rev10": "ts_sum(returns,10)",
 "rev60": "ts_sum(returns,60)",
 "hl_range":"divide(close - ts_min(low,20), ts_max(high,20) - ts_min(low,20))",  # stochastic %K (high->revert)
 "vol_rev":"divide(ts_sum(returns,5), ts_std_dev(returns,20))",  # vol-scaled reversal
}
def C():
 D={"decay":12,"truncation":0.10,"neutralization":"MARKET"}
 out=[]
 for name,anchor in A.items():
   out.append((f"g29_{name}", f"-1.0*{rk(anchor)}{QUAL}", dict(D)))
   out.append((f"g29_{name}_amp", f"signed_power(-1.0*{rk(anchor)}{QUAL},3)", dict(D)))
 return out
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D1_ANCHORS.json"; res=[]; cands=C()
    for i,(fam,expr,st) in enumerate(cands,1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== g29 [{i}/{len(cands)}] {fam} ===")
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
    print(f"D1 ANCHORS NON-OPTION (bar SH>1.25 TO<0.25 FIT>1.0 sc<0.7): SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<20}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
