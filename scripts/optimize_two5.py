"""Optimize-two round 5: SAILBOAT THE FINISH LINE.

Round 4 found f1d_gp50_mkt at SH 1.43 / FIT 1.04 -- passes 4 of 5 critical
checks (LOW_SHARPE, LOW_FITNESS, turnover, self-corr). Only CONCENTRATED_WEIGHT
remains. Round 5 attacks just that last check via:
 - Higher truncation (0.10, 0.12, 0.15)
 - Lower F1 weight (sparse signal that concentrates), heavier GP
 - Add extra dense diluter (book/price value)
 - Try SUBINDUSTRY in case MARKET's wide groups don't bound enough

Round 4 also found f2r_raw_dec8_t05 winners (3 variants) at SH 1.35-1.55,
FIT 1.22-1.29, blocked only by LOW_SUB_UNIVERSE_SHARPE. Fix that via
the same dilution + universe variants.

delay=1. STOP = no FAIL + sc<0.7 = SUBMIT.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

F1_CORE = "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)), 2)"
GP   = "group_rank(divide(ts_backfill(sales,250), ts_backfill(assets,250)), market)"
BV   = "group_rank(divide(ts_backfill(bookvalue_ps,250), close), market)"  # book/price value
ROA  = "group_rank(divide(ts_backfill(ebit,250), ts_backfill(assets,250)), market)"

BUZZ = "-ts_backfill(vec_sum(scl12_alltype_buzzvec), 20)"

def S(dec=8, tr=0.08, nt="MARKET"):
    return {"decay": dec, "truncation": tr, "neutralization": nt}

C = [
    # ===== F1: kill the last CONCENTRATED_WEIGHT on f1d_gp50_mkt =====
    # higher truncation
    ("f1f_gp50_mkt_t10",  f"0.5*{F1_CORE} + 0.5*{GP}",  S(8, 0.10, "MARKET")),
    ("f1f_gp50_mkt_t12",  f"0.5*{F1_CORE} + 0.5*{GP}",  S(8, 0.12, "MARKET")),
    ("f1f_gp50_mkt_t15",  f"0.5*{F1_CORE} + 0.5*{GP}",  S(8, 0.15, "MARKET")),
    # lower F1 weight (it's the sparse one)
    ("f1f_gp60_t10",      f"0.4*{F1_CORE} + 0.6*{GP}",  S(8, 0.10, "MARKET")),
    ("f1f_gp70_t10",      f"0.3*{F1_CORE} + 0.7*{GP}",  S(8, 0.10, "MARKET")),
    # add extra dense diluter (book/price)
    ("f1f_gp_bv",         f"0.5*{F1_CORE} + 0.3*{GP} + 0.2*{BV}", S(8, 0.10, "MARKET")),
    # sub-industry test (in case MARKET groups too wide)
    ("f1f_gp50_sub_t10",  f"0.5*{F1_CORE} + 0.5*{GP}",  S(8, 0.10, "SUBINDUSTRY")),

    # ===== F2: kill LOW_SUB_UNIVERSE_SHARPE via dilution =====
    # buzz + GP (lifts small-cap)
    ("f2f_buzz_gp_t10",     f"0.6*{BUZZ} + 0.4*{GP}",          S(8, 0.10, "INDUSTRY")),
    ("f2f_buzz_gp_t10_mkt", f"0.6*{BUZZ} + 0.4*{GP}",          S(8, 0.10, "MARKET")),
    # buzz + GP + ROA (extra dense)
    ("f2f_buzz_gp_roa",     f"0.6*{BUZZ} + 0.2*{GP} + 0.2*{ROA}", S(8, 0.10, "INDUSTRY")),
    # buzz heavier (preserve its SH 1.55 contribution)
    ("f2f_buzz70_gp30",     f"0.7*{BUZZ} + 0.3*{GP}",          S(8, 0.10, "INDUSTRY")),
    ("f2f_buzz80_gp20",     f"0.8*{BUZZ} + 0.2*{GP}",          S(8, 0.10, "INDUSTRY")),
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
    log.info(f"auth {cm.credentials.username}  OPT2 R5 (cross the finish line)")
    out=REPO/"WQ_OPT_TWO5.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== opt5 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr[:150]}")
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
    print("\n"+"="*110); print(f"OPT2 R5: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        print(f"  {r.family:<24} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:80]}")
    print("="*110); log.info(f"wrote {out}")
    return 0

if __name__=="__main__": sys.exit(main() or 0)
