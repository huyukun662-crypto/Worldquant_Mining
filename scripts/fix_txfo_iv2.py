"""Fix txfo x IV90 (round 2): STRUCTURAL fix. Output-backfill clears
WEIGHT_CONCENTRATION but kills SH (0.23) because the signal lives only
in freshly-reported names. Instead: backfill INPUTS to daily + use a
LONG corr window (>=60d) so each window spans a quarterly fundamental
update -> corr defined DENSELY for all names (diversified book) while
preserving the real txfo x IV relationship. delay=1, Industry neut."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
TX="ts_backfill(fnd6_txfo,250)"        # densify quarterly fundamental to daily (stepwise)
IV="ts_backfill(implied_volatility_call_90,20)"  # densify IV
def core(w): return f"ts_corr({TX}, {IV}, {w})"
def sig(w,g="subindustry"): return f"-group_rank({core(w)}, {g})"
C=[
 # long-window corr on densified inputs (window spans fundamental updates -> dense signal)
 ("g2_1_w60_t05", sig(60), {"decay":4,"truncation":0.05,"neutralization":"INDUSTRY"}),
 ("g2_2_w90_t05", sig(90), {"decay":4,"truncation":0.05,"neutralization":"INDUSTRY"}),
 ("g2_3_w120_t05", sig(120), {"decay":4,"truncation":0.05,"neutralization":"INDUSTRY"}),
 ("g2_4_w60_t08", sig(60), {"decay":4,"truncation":0.08,"neutralization":"INDUSTRY"}),
 ("g2_5_w90_t08_sub", sig(90), {"decay":4,"truncation":0.08,"neutralization":"SUBINDUSTRY"}),
 # decay smoothing + moderate window
 ("g2_6_w60_d8", sig(60), {"decay":8,"truncation":0.05,"neutralization":"INDUSTRY"}),
 # add light output backfill on top for full coverage
 ("g2_7_w60_bf10", f"-group_rank(ts_backfill({core(60)},10), subindustry)", {"decay":4,"truncation":0.05,"neutralization":"INDUSTRY"}),
 # market neut max diversification
 ("g2_8_w90_mkt", f"-group_rank({core(90)}, market)", {"decay":4,"truncation":0.06,"neutralization":"MARKET"}),
 # zscore the corr to tame outliers (extra concentration insurance)
 ("g2_9_w90_zsc", f"-group_rank(ts_zscore({core(90)},20), subindustry)", {"decay":4,"truncation":0.05,"neutralization":"INDUSTRY"}),
]
def wc(r):
    for c in r.checks:
        if "CONCENTRAT" in (c.get("name","").upper()): return c.get("result")
    return "n/a"
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_FIX_TXFO2.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== g2 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr}")
        r=submit(cm.session,fam,expr,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} WEIGHT_CONC={wc(r)} {r.alpha_id}")
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
                        and r.sharpe>1.25 and r.fitness>=1.0)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*125)
    print(f"FIX2 txfo x IV90 long-window (bar SH>1.25 FIT>1.0 sc<0.7 NO-FAIL): SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<18}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2} WC={wc(r):<5}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*125); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
