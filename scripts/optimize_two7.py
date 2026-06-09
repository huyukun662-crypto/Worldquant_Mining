"""Round 7: TRULY submittable -- attack root causes.

F1 CONCENTRATED root cause: F1's signed_power(zscore,2) magnitude ~16,
GP rank magnitude ~0.5 -- 32x mismatch, nominal 50/50 weights are
actually 99/1 after normalization. F1's optionable-only sparse names
dominate. FIX: scale() F1 before combining, or winsorize(zscore).

F2 LOW_SUB_UNIVERSE_SHARPE root cause: vec_sum(buzz_vec) is sparse in
small-caps (more NaN per stock). FIX: vec_avg or vec_count (rank-based),
denser social fields, or smoothed forms that survive NaN gaps.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

F1 = "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)), 2)"
F1_SCALED = "scale(signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)), 2))"
F1_NOAMP_SCALED = "scale(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)))"
# winsorize the inner zscore to bound F1 at ±3sigma BEFORE signed_power
F1_WINSORIZED = "signed_power(winsorize(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)), std=2.5), 2)"
F1_RANKED = "signed_power(rank(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)) - 0.5, 2)"

GP = "group_rank(divide(ts_backfill(sales,250), ts_backfill(assets,250)), market)"
BV = "group_rank(divide(ts_backfill(bookvalue_ps,250), close), market)"

# F2 attempts: replace vec_sum with vec_avg, vec_count
BUZZ_AVG = "-ts_backfill(vec_avg(scl12_alltype_buzzvec), 20)"
BUZZ_COUNT = "-ts_backfill(vec_count(scl12_alltype_buzzvec), 20)"
BUZZ_SUM = "-ts_backfill(vec_sum(scl12_alltype_buzzvec), 20)"   # original
# Use MATRIX buzz (no NaN per-stock issue from vec aggregation)
BUZZ_MATRIX = "-ts_backfill(scl12_buzz, 20)"
# Sentiment-weighted buzz (Ravenpack)
QCM = "vec_avg(nws18_qcm)"
# Densify with ts_mean over longer window
BUZZ_DENSE = "-ts_mean(ts_backfill(vec_sum(scl12_alltype_buzzvec), 60), 20)"

def S(dec=8, tr=0.05, nt="MARKET", uni="TOP3000"):
    return {"decay": dec, "truncation": tr, "neutralization": nt, "universe": uni}

C = [
    # ===== F1: scale + winsorize attacks =====
    ("f1h_scaled_gp50",   f"0.5*{F1_SCALED} + 0.5*{GP}",         S(8, 0.05, "MARKET")),
    ("f1h_noamp_scaled_gp50", f"0.5*{F1_NOAMP_SCALED} + 0.5*{GP}", S(8, 0.05, "MARKET")),
    ("f1h_winsor_gp50",   f"0.5*{F1_WINSORIZED} + 0.5*{GP}",    S(8, 0.05, "MARKET")),
    ("f1h_winsor_gp70",   f"0.3*{F1_WINSORIZED} + 0.7*{GP}",    S(8, 0.05, "MARKET")),
    ("f1h_ranked_gp50",   f"0.5*{F1_RANKED} + 0.5*{GP}",        S(8, 0.05, "MARKET")),
    ("f1h_winsor_gp_bv",  f"0.4*{F1_WINSORIZED} + 0.4*{GP} + 0.2*{BV}", S(8, 0.05, "MARKET")),

    # ===== F2: dense alternatives =====
    ("f2h_vec_avg",       BUZZ_AVG,                              S(8, 0.05, "INDUSTRY")),
    ("f2h_vec_avg_mkt",   BUZZ_AVG,                              S(8, 0.08, "MARKET")),
    ("f2h_vec_count",     BUZZ_COUNT,                            S(8, 0.05, "INDUSTRY")),
    ("f2h_matrix_dense",  BUZZ_MATRIX,                           S(8, 0.05, "INDUSTRY")),
    ("f2h_dense_smooth",  BUZZ_DENSE,                            S(8, 0.05, "INDUSTRY")),
]

def wname(r):
    return [c.get("name") for c in getattr(r,"checks",[]) if c.get("result")=="FAIL"]

def robust(sess, fam, expr, s):
    r=None
    for attempt in range(3):
        try:
            r=submit(sess, fam, expr, s)
            if (not r.ok) and r.error and ("CONCURRENT" in str(r.error) or "429" in str(r.error)):
                log.info(f"   concurrent wait 45s ({attempt+1}/3)"); time.sleep(45); continue
            return r
        except Exception as e:
            log.warning(f"   net {attempt+1}/3 {str(e)[:55]}"); time.sleep(20)
    return r

def main():
    cm=_load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  R7 root-cause attacks")
    out=REPO/"WQ_OPT_TWO7.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1
        log.info(f"=== r7 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr[:160]}")
        r=robust(cm.session, fam, expr, s)
        if r is None: continue
        if r.ok:
            try: sc,_,_=fetch_self_corr(cm.session, r.alpha_id, timeout_s=60); r.self_corr=sc
            except Exception: r.self_corr=None
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} sc={r.self_corr} FAIL={wname(r)}")
        else:
            log.warning(f"   FAILED: {str(r.error)[:130]}")
        res.append(r); json.dump([asdict(x) for x in res], open(out,"w"), indent=2)
    def ok_(r):
        return (r.ok and not wname(r) and (r.self_corr is None or abs(r.self_corr)<0.7) and r.sharpe>1.25)
    oks=sorted([r for r in res if r.ok], key=lambda r: r.sharpe, reverse=True)
    print("\n"+"="*110); print(f"R7: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        print(f"  {r.family:<24} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    print("="*110); log.info(f"wrote {out}")
    return 0

if __name__=="__main__": sys.exit(main() or 0)
