"""D1 round 27: push the winner e26.11 comboq_mkt (SH 1.28, TO 0.143,
FIT 0.98) past FIT>1.0. TO near 0.125 floor -> lever is RETURNS:
higher truncation (let winners run), heavier quality/value tilt,
signed_power amplification. Pure non-option. delay=1, MARKET neut."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log)
def rk(x): return f"group_rank({x},subindustry)"
ZC="ts_zscore(close,20)"
INV="divide(ts_backfill(capex,250),ts_backfill(assets,250))"
BV="divide(ts_backfill(bookvalue_ps,250),close)"
GP="divide(ts_backfill(sales,250)-ts_backfill(cogs,250),ts_backfill(assets,250))"
def Q(wz=1.0,wi=0.5,wb=0.3,wg=0.3): return f"{-wz}*{rk(ZC)}+{wi}*{rk(INV)}+{wb}*{rk(BV)}+{wg}*{rk(GP)}"
def cand(name,expr,dec=12,tr=0.08,uni="TOP3000"):
    return (name,expr,{"decay":dec,"truncation":tr,"neutralization":"MARKET","universe":uni})
C=[
 # truncation sweep on comboq_mkt (returns lever)
 cand("p27_1_t10", Q(), tr=0.10),
 cand("p27_2_t12", Q(), tr=0.12),
 cand("p27_3_t15", Q(), tr=0.15),
 # heavier quality/value tilt (higher-return components)
 cand("p27_4_qual_heavy", Q(wg=0.5), tr=0.10),
 cand("p27_5_valqual_heavy", Q(wb=0.5,wg=0.5), tr=0.10),
 # signed_power amplify the composite (concentrate conviction)
 cand("p27_6_amp", f"signed_power({Q()},3)", tr=0.10),
 cand("p27_7_amp_t12", f"signed_power({Q()},3)", tr=0.12),
 # decay8 (less smoothing -> more SH, watch TO) + higher trunc
 cand("p27_8_dec8_t10", Q(), dec=8, tr=0.10),
 # TOP1000 (often higher returns) + comboq
 cand("p27_9_t1000_t10", Q(), tr=0.10, uni="TOP1000"),
 cand("p27_10_t1000_qual", Q(wg=0.5), tr=0.10, uni="TOP1000"),
 # quality+value heavy, decay8, trunc0.12
 cand("p27_11_vq_dec8_t12", Q(wb=0.5,wg=0.5), dec=8, tr=0.12),
 # amp + qual heavy
 cand("p27_12_amp_qual", f"signed_power({Q(wg=0.5)},3)", tr=0.10),
]
def main():
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}")
    out=REPO/"WQ_D1_PUSH.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== p27 [{i}/{len(C)}] {fam} (uni={s['universe']} tr={s['truncation']}) ===")
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
    print(f"D1 PUSH NON-OPTION (bar SH>1.25 TO<0.25 FIT>1.0 sc<0.7): SUBMITTABLE={sum(1 for r in ok if ok_(r))}/{len(ok)} OK")
    for i,r in enumerate(ok,1):
        sc=f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<3}{r.family:<22}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {'*** SUBMIT ***' if ok_(r) else 'no':<14} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {r.error[:80]}")
    print("="*120); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
