"""Optimize-two round 3: structural fix for CONCENTRATED_WEIGHT.

Round 2 verdict: every minimal-fix variant of f1_v0 cleared LOW_SHARPE
(SH 1.31-1.62) but STILL failed LOW_FITNESS (FIT 0.90-0.93) and
CONCENTRATED_WEIGHT regardless of decay/truncation/neut.

Root cause: signed_power(zscore(x), 2) is UNBOUNDED. zscore can be
big (e.g., 5 stdev), signed_power squares it (25), even truncation
0.10 can't keep weights bounded for the few extreme names. Same
mechanism caps FIT around 0.93.

Fix: replace zscore with group_rank (bounded [0,1]) so signed_power
operates on a bounded input -- preserves the signal shape but kills
the weight concentration. OR scale-then-truncate after signed_power.

delay=1, signal direction unchanged. STOP = no FAIL + sc<0.7.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

INNER = "ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)"
# Two-sided idea-faithful
INNER2 = "ts_decay_linear((ts_delta(implied_volatility_call_60,25)>0) - (ts_delta(implied_volatility_put_60,25)>0), 25)"

QCM="vec_avg(nws18_qcm)"; SCL_SENT="scl12_sentiment"; SCL_BUZZ_M="scl12_buzz"

def S(dec=4, tr=0.05, nt="INDUSTRY"):
    return {"decay": dec, "truncation": tr, "neutralization": nt}

C = [
    # ===== F1: bound the signal with group_rank instead of zscore =====
    ("f1b_grouprank_amp2",
     f"signed_power(group_rank({INNER}, industry) - 0.5, 2)",
     S(8, 0.05, "INDUSTRY")),
    ("f1b_grouprank_amp3",
     f"signed_power(group_rank({INNER}, industry) - 0.5, 3)",
     S(8, 0.05, "INDUSTRY")),
    ("f1b_grouprank_sub",
     f"signed_power(group_rank({INNER}, subindustry) - 0.5, 2)",
     S(8, 0.05, "SUBINDUSTRY")),
    ("f1b_grouprank_mkt",
     f"signed_power(group_rank({INNER}, market) - 0.5, 2)",
     S(8, 0.08, "MARKET")),
    # use rank() (cross-sectional, [0,1]) instead of zscore
    ("f1b_rank_amp2",
     f"signed_power(rank({INNER}) - 0.5, 2)",
     S(8, 0.05, "INDUSTRY")),
    # Drop signed_power entirely -- just zscore + truncation does the job
    ("f1b_zscore_only",
     f"zscore({INNER})",
     S(4, 0.05, "INDUSTRY")),
    # scale the output to bound + outer ts_decay smoothing
    ("f1b_scale_decay",
     f"scale(signed_power(zscore({INNER}), 2))",
     S(8, 0.05, "INDUSTRY")),

    # ===== F1 two-sided with the bounded fix =====
    ("f1tb_grouprank_amp2",
     f"signed_power(group_rank({INNER2}, industry) - 0.5, 2)",
     S(8, 0.05, "INDUSTRY")),
    ("f1tb_grouprank_sub",
     f"signed_power(group_rank({INNER2}, subindustry) - 0.5, 2)",
     S(8, 0.05, "SUBINDUSTRY")),

    # ===== F2: keep raw vec_sum but tune settings (no group_rank, which killed it) =====
    # decay8 + trunc05 to lift FIT, raw signal preserved
    ("f2r_raw_dec8_t05",
     f"-ts_backfill(vec_sum(scl12_alltype_buzzvec), 20)",
     S(8, 0.05, "INDUSTRY")),
    ("f2r_raw_dec12_t08",
     f"-ts_backfill(vec_sum(scl12_alltype_buzzvec), 20)",
     S(12, 0.08, "INDUSTRY")),
    # raw + MARKET neut
    ("f2r_raw_dec8_mkt",
     f"-ts_backfill(vec_sum(scl12_alltype_buzzvec), 20)",
     S(8, 0.08, "MARKET")),
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
    log.info(f"auth {cm.credentials.username}  OPT2 R3 (structural fix: bound signed_power)")
    out=REPO/"WQ_OPT_TWO3.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== opt3 [{i}/{len(C)}] {fam} ===")
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
    print("\n"+"="*110); print(f"OPT2 R3: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        print(f"  {r.family:<24} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:80]}")
    print("="*110); log.info(f"wrote {out}")
    return 0

if __name__=="__main__": sys.exit(main() or 0)
