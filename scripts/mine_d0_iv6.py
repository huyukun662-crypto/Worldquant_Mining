"""D0 round 24: around the WINNER (A1kPmVqg: TOP3000, g60, IV60 skew, p3,
SH 2.03). Push even looser gates (50/55th) + tenor variants on TOP3000
to find higher-SH and additional uncorrelated submittable D0s. delay=0."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def q(x): return f"quantile({x})"
IV60="ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5)"
IV30="ts_backfill(implied_volatility_call_30 - implied_volatility_put_30, 5)"
IV90="ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 5)"
IV120="ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5)"
def G(th): return f"gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > {th});"
def b(score,th,p=3,dec=4,tr=0.02,nt="SUBINDUSTRY"):
    return (f"score={score};\n{G(th)}\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,{p}),5), -1)",
            {"decay":dec,"truncation":tr,"neutralization":nt})
C=[
 # even looser gates on the winner (g60 gave 2.03)
 ("a24_1_g55", *b(q(IV60),0.55)), ("a24_2_g50", *b(q(IV60),0.50)),
 ("a24_3_g45", *b(q(IV60),0.45)), ("a24_4_g60_p4", *b(q(IV60),0.60,4)),
 # tenor variants at g60 on TOP3000 (uncorrelated submittable candidates)
 ("a24_5_iv30_g60", *b(q(IV30),0.60)), ("a24_6_iv90_g60", *b(q(IV90),0.60)),
 ("a24_7_iv120_g60", *b(q(IV120),0.60)),
 # multi-tenor averaged at g60
 ("a24_8_avg_g60", *b(f"0.4*{q(IV30)}+0.4*{q(IV60)}+0.2*{q(IV90)}",0.60)),
 # winner with INDUSTRY / MARKET neut (diversify)
 ("a24_9_g60_ind", *b(q(IV60),0.60,nt="INDUSTRY")),
 ("a24_10_g60_mkt", *b(q(IV60),0.60,tr=0.03,nt="MARKET")),
 # g55 p4 and decay tweak
 ("a24_11_g55_p4", *b(q(IV60),0.55,4)), ("a24_12_g60_dec3", *b(q(IV60),0.60,dec=3)),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_IV6.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== a24 [{i}/{len(C)}] {fam} ===")
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
    print("\n"+"="*120); print(f"D0 IV6: SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<18}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:70]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
