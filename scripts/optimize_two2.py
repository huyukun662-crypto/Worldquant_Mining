"""Optimize-two round 2: MINIMAL FIX of user's original factors.

Round 1 verdict: user's f1_v0 (the IV call >0 boolean) already passes
LOW_SHARPE (SH 1.58); only LOW_FITNESS (0.88) and CONCENTRATED_WEIGHT
need fixing. Don't change the SIGNAL -- change SETTINGS: higher decay
cuts TO (lifts FIT), higher truncation kills weight concentration.
The call-put differential approach (v2-v5) was wrong direction.

For factor 2 (buzz), round 1 still running -- this round 2 focuses
on factor 1 minimal fixes + a couple more buzz variants.

delay=1, no signal modifications. STOP = no FAIL + sc<0.7.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

# === Factor 1: user's EXACT original signal, varying ONLY decay/truncation/neut ===
F1 = "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)), 2)"
# Also test ADDING put IV but keeping the >0 boolean structure (the IDEA's two-sided version)
F1_TWO_SIDED = "signed_power(zscore(ts_decay_linear((ts_delta(implied_volatility_call_60,25)>0) - (ts_delta(implied_volatility_put_60,25)>0), 25)), 2)"

QCM="vec_avg(nws18_qcm)"; SCL_SENT="scl12_sentiment"; SCL_BUZZ_M="scl12_buzz"

def S(dec=0, tr=0.01, nt="INDUSTRY"):
    return {"decay": dec, "truncation": tr, "neutralization": nt}

C = [
    # ===== FACTOR 1 MINIMAL FIXES (exact signal, settings tuned) =====
    # baseline failed on LOW_FITNESS(0.88) + CONCENTRATED_WEIGHT
    # math: FIT = SH * sqrt(ret/max(TO,0.125)). cut TO 0.30 -> 0.125 => FIT 0.88*1.55 = 1.36
    ("f1m_decay8_t05",     F1, S(8, 0.05, "INDUSTRY")),         # heavy decay (cuts TO) + trunc 0.05
    ("f1m_decay12_t05",    F1, S(12, 0.05, "INDUSTRY")),        # heavier decay
    ("f1m_decay8_t08",     F1, S(8, 0.08, "INDUSTRY")),         # more truncation slack
    ("f1m_decay8_t05_sub", F1, S(8, 0.05, "SUBINDUSTRY")),      # narrower neut groups
    ("f1m_decay8_t10_mkt", F1, S(8, 0.10, "MARKET")),           # max diversification

    # ===== FACTOR 1 TWO-SIDED (idea-faithful) with proper settings =====
    ("f1ts_decay8_t05",     F1_TWO_SIDED, S(8, 0.05, "INDUSTRY")),
    ("f1ts_decay8_t05_sub", F1_TWO_SIDED, S(8, 0.05, "SUBINDUSTRY")),
    ("f1ts_decay12_t08_mkt", F1_TWO_SIDED, S(12, 0.08, "MARKET")),

    # ===== FACTOR 2 (compact, in case round 1 doesn't have a winner) =====
    # original was raw vec_sum buzz (sparse). Try: backfill more aggressively + smooth + rank
    ("f2m_bf60_sm20_grp",   f"-group_rank(ts_mean(ts_backfill({SCL_BUZZ_M}, 60), 20), industry)", S(8, 0.05, "INDUSTRY")),
    ("f2m_bf60_sm20_mkt",   f"-group_rank(ts_mean(ts_backfill({SCL_BUZZ_M}, 60), 20), market)", S(8, 0.08, "MARKET")),
    # combine low-buzz with positive QCM sentiment (two orthogonal sentiment signals)
    ("f2m_buzz_x_qcmpos",   f"-group_rank(ts_mean(ts_backfill({SCL_BUZZ_M}, 60), 20), industry) + 0.5*group_rank(ts_mean(ts_backfill({QCM}, 60), 20), industry)", S(8, 0.05, "INDUSTRY")),
    # low-buzz + QCM-reversal (round 2 sentiment finding)
    ("f2m_buzz_x_qcmrev",   f"-group_rank(ts_mean(ts_backfill({SCL_BUZZ_M}, 60), 20), industry) - 0.5*group_rank(ts_mean(ts_backfill({QCM}, 60), 20), industry)", S(8, 0.05, "INDUSTRY")),
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
    log.info(f"auth {cm.credentials.username}  OPT2 R2 (minimal fixes for user factors)")
    out=REPO/"WQ_OPT_TWO2.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== opt2 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr[:140]}")
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
    print("\n"+"="*110); print(f"OPT2 R2: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        print(f"  {r.family:<24} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:80]}")
    print("="*110); log.info(f"wrote {out}")
    return 0

if __name__=="__main__": sys.exit(main() or 0)
