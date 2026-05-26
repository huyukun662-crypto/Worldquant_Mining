"""D0 round 21: exponent + gate optimization around IV60 amp5 (SH 1.92).
v19.10 (amp5) = SH 1.92, FIT 2.53. Trend: higher signed_power exp -> higher SH.
Push exponent 5-9 + tighter gate to clear SH>2.0. delay=0."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def q(x): return f"quantile({x})"
IV60="ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5)"
G80="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.80);"
G90="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.90);"
G85="gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.85);"
def sp(p): return f"signed_power(score-0.5,{p})"
def cand(name,g,p,dec=4,tr=0.02,nt="SUBINDUSTRY"):
    return (name, f"score={q(IV60)};\n{g}\ntrade_when(gate, ts_decay_linear({sp(p)},5), -1)", {"decay":dec,"truncation":tr,"neutralization":nt})
C=[
 cand("x21_1_g80_p6",G80,6), cand("x21_2_g80_p7",G80,7),
 cand("x21_3_g85_p5",G85,5), cand("x21_4_g85_p6",G85,6),
 cand("x21_5_g90_p5",G90,5), cand("x21_6_g90_p6",G90,6),
 cand("x21_7_g80_p5_t01",G80,5,tr=0.01), cand("x21_8_g80_p5_dec2",G80,5,dec=2),
 cand("x21_9_g85_p7",G85,7), cand("x21_10_g80_p5_ind",G80,5,nt="INDUSTRY"),
 cand("x21_11_g90_p7",G90,7), cand("x21_12_g85_p5_t01",G85,5,tr=0.01),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D0_IV3.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== x21 [{i}/{len(C)}] {fam} ===")
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
    print("\n"+"="*120); print(f"D0 IV3: SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<20}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:70]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
