"""D0 round 22: looser gate (70/75th) x exponent sweep -- w20.1 (g70) hit
SH 1.95, the best. Looser gate + tuned exponent to clear SH>2.0. delay=0."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def q(x): return f"quantile({x})"
IV60="ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5)"
def G(th): return f"gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > {th});"
def cand(name,th,p,dec=4,tr=0.02,nt="SUBINDUSTRY"):
    return (name, f"score={q(IV60)};\n{G(th)}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,{p}),5), -1)", {"decay":dec,"truncation":tr,"neutralization":nt})
C=[
 cand("y22_1_g70_p4",0.70,4), cand("y22_2_g70_p5",0.70,5),
 cand("y22_3_g65_p3",0.65,3), cand("y22_4_g65_p4",0.65,4),
 cand("y22_5_g75_p3",0.75,3), cand("y22_6_g75_p4",0.75,4),
 cand("y22_7_g70_p3_t01",0.70,3,tr=0.01), cand("y22_8_g70_p3_t03",0.70,3,tr=0.03),
 cand("y22_9_g70_p3_dec2",0.70,3,dec=2), cand("y22_10_g70_p3_dec6",0.70,3,dec=6),
 cand("y22_11_g60_p3",0.60,3), cand("y22_12_g70_p4_t01",0.70,4,tr=0.01),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_IV4.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== y22 [{i}/{len(C)}] {fam} ===")
        r=submit(cm.session,fam,expr,s); res.append(r)
        if r.ok: log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} {r.alpha_id}")
        else: log.warning(f"   FAILED: {r.error[:130]}")
        json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    log.info("=== pass2 self-corr ===")
    for r in res:
        if not r.ok or not r.alpha_id: continue
        sc,top,stt=fetch_self_corr(cm.session,r.alpha_id,timeout_s=120); r.self_corr=sc
        if top: r.self_corr_peer=top.get("id"); r.self_corr_peer_sharpe=top.get("sharpe")
        log.info(f"   {r.alpha_id} sc={sc} ({stt})")
    json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def ok_(r): return (r.ok and not any(c.get("result")=="FAIL" for c in r.checks)
                        and (r.self_corr is None or abs(r.self_corr)<0.7) and r.sharpe>2.0 and r.fitness>=1.3)
    ok=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*120); print(f"D0 IV4: SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<18}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:70]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
