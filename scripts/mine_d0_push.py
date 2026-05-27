"""D0 round 31: micro-tune around h30.7 (quality-heavy amp MARKET d8 t08:
SH 1.27/TO 0.153/FIT 0.94) to push FIT>1.0 -> standard-bar-submittable D0
non-option. TO near floor, so lever is RETURNS: add cashflow profitability,
heavier quality, decay/trunc tweaks, vector/regression neut. delay=0,
pure pv+fundamental."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def bf(f,n=250): return f"ts_backfill({f},{n})"
def rk(x): return f"group_rank({x},subindustry)"
Z="ts_zscore(close,20)"
INV=f"divide({bf('capex')},{bf('assets')})"
VAL=f"divide({bf('bookvalue_ps')},close)"
GP=f"divide({bf('sales')}-{bf('cogs')},{bf('assets')})"
CFOA=f"divide({bf('cashflow_op')},{bf('assets')})"
ROA=f"divide({bf('ebit')},{bf('assets')})"
def expr(wi=0.5,wb=0.5,wg=0.5,wc=0.0,wr=0.0,amp=3):
    s=f"-1.0*{rk(Z)}+{wi}*{rk(INV)}+{wb}*{rk(VAL)}+{wg}*{rk(GP)}"
    if wc: s+=f"+{wc}*{rk(CFOA)}"
    if wr: s+=f"+{wr}*{rk(ROA)}"
    return f"signed_power({s},{amp})" if amp else s
M="MARKET"
def C():
 return [
 # h30.7 baseline + cashflow profitability (more return)
 ("i31_1_cfo",     expr(wc=0.5), {"decay":8,"truncation":0.08,"neutralization":M}),
 ("i31_2_cfo_roa", expr(wc=0.5,wr=0.3), {"decay":8,"truncation":0.08,"neutralization":M}),
 # heavier quality weights
 ("i31_3_q06",     expr(wi=0.6,wb=0.6,wg=0.7), {"decay":8,"truncation":0.08,"neutralization":M}),
 # decay tweaks around 8
 ("i31_4_dec6",    expr(wc=0.5), {"decay":6,"truncation":0.08,"neutralization":M}),
 ("i31_5_dec10",   expr(wc=0.5), {"decay":10,"truncation":0.08,"neutralization":M}),
 # truncation up (let winners run -> returns up)
 ("i31_6_t10",     expr(wc=0.5), {"decay":8,"truncation":0.10,"neutralization":M}),
 ("i31_7_t12",     expr(wc=0.5), {"decay":8,"truncation":0.12,"neutralization":M}),
 # full quality stack (GP+CFOA+ROA), drop value
 ("i31_8_qstack",  expr(wb=0.0,wg=0.6,wc=0.6,wr=0.4), {"decay":8,"truncation":0.10,"neutralization":M}),
 # exponent 2 (less aggressive amp, may lift SH)
 ("i31_9_amp2",    expr(wc=0.5,amp=2), {"decay":8,"truncation":0.08,"neutralization":M}),
 # dec6 + t10 (returns lever combined)
 ("i31_10_dec6_t10",expr(wc=0.5), {"decay":6,"truncation":0.10,"neutralization":M}),
 # heavier quality + cashflow + t10
 ("i31_11_qheavy_cfo_t10", expr(wi=0.6,wb=0.6,wg=0.7,wc=0.5), {"decay":8,"truncation":0.10,"neutralization":M}),
 # all-quality stack dec6 t10
 ("i31_12_qstack_dec6", expr(wb=0.0,wg=0.6,wc=0.6,wr=0.4), {"decay":6,"truncation":0.10,"neutralization":M}),
 ]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_PUSH.json"; res=[]; cands=C()
    for i,(fam,expr_,st) in enumerate(cands,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== i31 [{i}/{len(cands)}] {fam} ===")
        r=submit(cm.session,fam,expr_,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} {r.alpha_id}")
        else: log.warning(f"   FAILED: {r.error[:140]}")
        json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    log.info("=== pass2 self-corr ===")
    for r in res:
        if not r.ok or not r.alpha_id: continue
        sc,top,stt=fetch_self_corr(cm.session,r.alpha_id,timeout_s=120); r.self_corr=sc
        log.info(f"   {r.alpha_id} sc={sc} ({stt})")
    json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def std(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7)
                        and r.sharpe>1.25 and r.turnover<0.25 and r.fitness>=1.0)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.fitness,reverse=True)
    print("\n"+"="*120)
    print(f"D0 PUSH NON-OPTION (std bar SH>1.25 TO<0.25 FIT>1.0 sc<0.7): SUBMITTABLE={sum(1 for r in ok if std(r))}/{len(ok)}")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if std(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
