"""Optimize-two round 4: DILUTE sparse IV signal with dense quality signal.

Definitive finding from rounds 2-3: CONCENTRATED_WEIGHT on F1 is
structural — `ts_delta(IV_call,25)>0` is intrinsically sparse (few
names with persistent IV-up). NO truncation/decay/neut variant fixes
it; even bounded inputs (group_rank, rank) still concentrate.

The only structural cure: combine the sparse F1 signal with a DENSE
high-quality signal at substantial weight (50%+). gross-profitability
`(sales/assets)` is dense (all stocks have it) and orthogonal —
adding it spreads weight across the universe while preserving the
F1 directional info.

delay=1, no signal direction changes. STOP = no FAIL + sc<0.7 = SUBMIT.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

# F1 winning core: user's exact signal (yields SH 1.62 alone, fails concentration)
F1_CORE = "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)), 2)"
# Bounded variant for combinations (lower SH but cleaner weights)
F1_BOUNDED = "signed_power(group_rank(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25), industry) - 0.5, 2)"
# Plain zscore (no signed_power) -- SH 1.36 in round 3
F1_PLAIN = "zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25))"

# Dense signals to dilute with
GP = "group_rank(divide(ts_backfill(sales,250), ts_backfill(assets,250)), market)"        # gross profitability
CAPEX = "-group_rank(divide(ts_backfill(capex,250), ts_backfill(assets,250)), market)"     # low capex/assets
ROA  = "group_rank(divide(ts_backfill(ebit,250),  ts_backfill(assets,250)), market)"      # profitability

QCM = "vec_avg(nws18_qcm)"   # for F2 combos

def S(dec=4, tr=0.05, nt="INDUSTRY"):
    return {"decay": dec, "truncation": tr, "neutralization": nt}

C = [
    # ===== F1 DILUTED with gross-profitability (50/50 to 70/30) =====
    ("f1d_gp50_dec8",   f"0.5*{F1_CORE} + 0.5*{GP}",     S(8, 0.05, "INDUSTRY")),
    ("f1d_gp30_dec8",   f"0.7*{F1_CORE} + 0.3*{GP}",     S(8, 0.05, "INDUSTRY")),
    ("f1d_gp50_mkt",    f"0.5*{F1_CORE} + 0.5*{GP}",     S(8, 0.08, "MARKET")),
    # Bounded F1 + GP (lower SH but cleaner)
    ("f1d_bnd_gp50",    f"0.5*{F1_BOUNDED} + 0.5*{GP}",  S(8, 0.05, "INDUSTRY")),
    # Plain F1 (no signed_power, SH 1.36) + GP
    ("f1d_plain_gp50",  f"0.5*{F1_PLAIN} + 0.5*{GP}",    S(8, 0.05, "INDUSTRY")),
    ("f1d_plain_gp30",  f"0.7*{F1_PLAIN} + 0.3*{GP}",    S(8, 0.05, "INDUSTRY")),
    # Plain F1 + ROA
    ("f1d_plain_roa50", f"0.5*{F1_PLAIN} + 0.5*{ROA}",   S(8, 0.05, "INDUSTRY")),
    # Plain F1 + GP + ROA (richer quality)
    ("f1d_plain_gp_roa", f"0.5*{F1_PLAIN} + 0.3*{GP} + 0.3*{ROA}", S(8, 0.05, "INDUSTRY")),
    # Plain F1 + GP, MARKET neut
    ("f1d_plain_gp_mkt", f"0.5*{F1_PLAIN} + 0.5*{GP}",   S(8, 0.08, "MARKET")),

    # ===== F2 diluted with GP (in case F2 alone is hopeless) =====
    ("f2d_buzz_gp50",   f"-0.5*ts_backfill(vec_sum(scl12_alltype_buzzvec), 20) + 0.5*{GP}", S(8, 0.05, "INDUSTRY")),
    # F2 paired with QCM-reversal AND GP (triple ensemble)
    ("f2d_buzz_qcm_gp", f"-0.3*ts_backfill(vec_sum(scl12_alltype_buzzvec), 20) - 0.3*group_rank(ts_mean(ts_backfill({QCM},60),20), industry) + 0.4*{GP}", S(8, 0.05, "INDUSTRY")),
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
    log.info(f"auth {cm.credentials.username}  OPT2 R4 (DILUTE sparse F1 with dense quality)")
    out=REPO/"WQ_OPT_TWO4.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== opt4 [{i}/{len(C)}] {fam} ===")
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
    print("\n"+"="*110); print(f"OPT2 R4: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        print(f"  {r.family:<22} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:80]}")
    print("="*110); log.info(f"wrote {out}")
    return 0

if __name__=="__main__": sys.exit(main() or 0)
