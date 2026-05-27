"""Fix the txfo x IV90 corr alpha: SH 1.90/FIT 2.65 but FAILs
WEIGHT_CONCENTRATION (50%>10% on 7/13/2023). Root cause = sparse
coverage (quarterly fnd6_txfo x optionable-only IV90 -> tiny book).
Fix = ts_backfill the corr OUTPUT to broaden coverage + lower
truncation + decay smoothing. delay=1, Industry neut (matches UI)."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
CORE="ts_corr(ts_delay(fnd6_txfo,1), ts_delay(implied_volatility_call_90,1), 10)"
def sig(bf,g="subindustry"): return f"-group_rank(ts_backfill({CORE},{bf}), {g})"
C=[
 # baseline reproduce (original, no fix) -- expect WEIGHT_CONCENTRATION FAIL
 ("fix_v0_orig", f"-1 * group_rank({CORE}, subindustry)", {"decay":2,"truncation":0.08,"neutralization":"INDUSTRY"}),
 # backfill output coverage + lower trunc + decay
 ("fix_v1_bf20_t05_d2", sig(20), {"decay":2,"truncation":0.05,"neutralization":"INDUSTRY"}),
 ("fix_v2_bf20_t03_d4", sig(20), {"decay":4,"truncation":0.03,"neutralization":"INDUSTRY"}),
 ("fix_v3_bf40_t02_d4", sig(40), {"decay":4,"truncation":0.02,"neutralization":"INDUSTRY"}),
 ("fix_v4_bf60_t02_d6", sig(60), {"decay":6,"truncation":0.02,"neutralization":"INDUSTRY"}),
 # truncation-only (isolate: does low trunc alone fix it?)
 ("fix_v5_t02_nobf_d4", f"-1 * group_rank({CORE}, subindustry)", {"decay":4,"truncation":0.02,"neutralization":"INDUSTRY"}),
 # densify inputs too (backfill stale fundamentals/IV) + output backfill
 ("fix_v6_bfin_out", f"-group_rank(ts_backfill(ts_corr(ts_delay(ts_backfill(fnd6_txfo,120),1), ts_delay(ts_backfill(implied_volatility_call_90,20),1), 10),20), subindustry)",
   {"decay":4,"truncation":0.03,"neutralization":"INDUSTRY"}),
 # subindustry neut variant of the best-shape fix
 ("fix_v7_bf40_t03_sub", sig(40), {"decay":4,"truncation":0.03,"neutralization":"SUBINDUSTRY"}),
 # market neut high coverage (max diversification)
 ("fix_v8_bf60_t02_mkt", sig(60,"market"), {"decay":4,"truncation":0.03,"neutralization":"MARKET"}),
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
    out=REPO/"WQ_FIX_TXFO.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== fix [{i}/{len(C)}] {fam} ===")
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
    print(f"FIX txfo x IV90 (bar SH>1.25 FIT>1.0 sc<0.7 NO-FAIL): SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2} WC={wc(r):<5}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*125); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
