"""Optimize-two round 6: cross the finish line definitively.

R5 leaders:
 F1: f1f_gp70_t10 SH 1.54 FIT 1.23 sc 0.12 -- only CONCENTRATED_WEIGHT
 F2: f2r_raw_dec8_t05 SH 1.55 FIT 1.29 sc 0.27 -- only LOW_SUB_UNIVERSE_SHARPE

R6 attacks each single remaining check:
 F1 CONCENTRATED: very tight truncation (0.02), extreme GP weight (90%),
   add SECOND dense diluter, vector_neut against GP
 F2 LOW_SUB_UNIVERSE_SHARPE: try TOP1000 universe (less small-cap),
   try MARKET + higher trunc, try simpler signal-only forms
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

F1 = "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)), 2)"
GP = "group_rank(divide(ts_backfill(sales,250), ts_backfill(assets,250)), market)"
BV = "group_rank(divide(ts_backfill(bookvalue_ps,250), close), market)"
ROA = "group_rank(divide(ts_backfill(ebit,250), ts_backfill(assets,250)), market)"
BUZZ = "-ts_backfill(vec_sum(scl12_alltype_buzzvec), 20)"

def S(dec=8, tr=0.05, nt="MARKET", uni="TOP3000"):
    return {"decay": dec, "truncation": tr, "neutralization": nt, "universe": uni}

C = [
    # ===== F1: kill CONCENTRATED with extreme dilution / vector_neut =====
    ("f1g_gp80_t10",        f"0.2*{F1} + 0.8*{GP}",                                S(8, 0.10, "MARKET")),
    ("f1g_gp90_t10",        f"0.1*{F1} + 0.9*{GP}",                                S(8, 0.10, "MARKET")),
    # very tight truncation (force per-name <= 2%)
    ("f1g_gp70_t02",        f"0.3*{F1} + 0.7*{GP}",                                S(8, 0.02, "MARKET")),
    # two dense diluters (GP + BV) to lift sub-universe too
    ("f1g_gp_bv_2d",        f"0.3*{F1} + 0.4*{GP} + 0.3*{BV}",                     S(8, 0.08, "MARKET")),
    ("f1g_gp_bv_roa",       f"0.2*{F1} + 0.3*{GP} + 0.3*{BV} + 0.2*{ROA}",         S(8, 0.08, "MARKET")),
    # vector_neut: project F1 onto orthogonal-to-GP space
    ("f1g_vecneut_gp",      f"vector_neut({F1}, {GP})",                            S(8, 0.05, "MARKET")),
    ("f1g_vn_plus_gp",      f"vector_neut({F1}, {GP}) + 0.5*{GP}",                 S(8, 0.05, "MARKET")),

    # ===== F2: kill LOW_SUB_UNIVERSE_SHARPE via universe shift =====
    # raw buzz at TOP1000 (less small-cap)
    ("f2g_raw_top1000",     BUZZ,                                                  S(8, 0.05, "INDUSTRY", "TOP1000")),
    # raw buzz at TOP500
    ("f2g_raw_top500",      BUZZ,                                                  S(8, 0.05, "INDUSTRY", "TOP500")),
    # raw buzz MARKET + bigger trunc
    ("f2g_raw_mkt_t10",     BUZZ,                                                  S(8, 0.10, "MARKET")),
    # buzz + low-vol (lifts sub-universe Sharpe via low-vol anomaly)
    ("f2g_buzz_lowvol",     f"0.6*{BUZZ} - 0.4*group_rank(ts_std_dev(returns,60), market)",
                                                                                   S(8, 0.05, "INDUSTRY")),
    # buzz + low-vol + GP triple
    ("f2g_buzz_lv_gp",      f"0.5*{BUZZ} - 0.25*group_rank(ts_std_dev(returns,60), market) + 0.25*{GP}",
                                                                                   S(8, 0.05, "INDUSTRY")),
]

def wname(r):
    return [c.get("name") for c in getattr(r,"checks",[]) if c.get("result")=="FAIL"]

def robust(sess, fam, expr, s):
    r=None
    for attempt in range(6):
        try:
            r=submit(sess, fam, expr, s)
            if (not r.ok) and r.error and ("CONCURRENT" in str(r.error) or "429" in str(r.error)):
                log.info(f"   concurrent wait 60s ({attempt+1}/6)"); time.sleep(60); continue
            return r
        except Exception as e:
            log.warning(f"   net {attempt+1}/6 {str(e)[:55]}"); time.sleep(25)
    return r

def main():
    cm=_load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  OPT2 R6 (finish line)")
    out=REPO/"WQ_OPT_TWO6.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1
        log.info(f"=== opt6 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr[:160]}")
        r=robust(cm.session, fam, expr, s)
        if r is None: continue
        if r.ok:
            try: sc,_,_=fetch_self_corr(cm.session, r.alpha_id, timeout_s=90); r.self_corr=sc
            except Exception: r.self_corr=None
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} sc={r.self_corr} FAIL={wname(r)}")
        else: log.warning(f"   FAILED: {str(r.error)[:130]}")
        res.append(r); json.dump([asdict(x) for x in res], open(out,"w"), indent=2)
    def ok_(r): return (r.ok and not wname(r) and (r.self_corr is None or abs(r.self_corr)<0.7) and r.sharpe>1.25)
    oks=sorted([r for r in res if r.ok], key=lambda r: r.sharpe, reverse=True)
    print("\n"+"="*110); print(f"OPT2 R6: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        print(f"  {r.family:<22} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:80]}")
    print("="*110); log.info(f"wrote {out}")
    return 0

if __name__=="__main__": sys.exit(main() or 0)
