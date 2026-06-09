"""Optimize two user-specified factors to submittable.

(1) IV change momentum (delay=1):
    signed_power(zscore(ts_decay_linear(ts_delta(IV_call_60,25)>0, 25)), 2)
    Idea: large call-IV increase -> high returns; large put-IV increase -> low returns
    Issues: uses ONLY call (idea mentions both); >0 boolean throws away magnitude.

(2) Social buzz fade (delay=1):
    -ts_backfill(vec_sum(scl12_alltype_buzzvec), 20)
    Idea: low buzz -> less overreaction -> invest
    Issues: per idea, sparse NaN -> low SH / high TO; no cross-sectional rank.

delay=1, Industry neut, truncation=0.01 (matches user spec).
STOP = no FAIL on WQ checks AND |self_corr| < 0.7 = submittable.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

BUZZ_VEC="scl12_alltype_buzzvec"
SCL_SENT="scl12_sentiment"
SCL_BUZZ_M="scl12_buzz"
QCM="vec_avg(nws18_qcm)"

def S(dec=0, tr=0.01, nt="INDUSTRY"):
    return {"decay": dec, "truncation": tr, "neutralization": nt}

C = [
    # ===== FACTOR 1: IV change momentum =====
    ("f1_v0_orig",
     "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25)>0, 25)), 2)",
     S(0, 0.01)),
    ("f1_v1_raw_delta",
     "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25), 25)), 2)",
     S(0, 0.01)),
    ("f1_v2_call_minus_put",
     "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25) - ts_delta(implied_volatility_put_60,25), 25)), 2)",
     S(0, 0.01)),
    ("f1_v3_w10",
     "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,10) - ts_delta(implied_volatility_put_60,10), 10)), 2)",
     S(0, 0.01)),
    ("f1_v4_grouprank",
     "signed_power(group_rank(ts_decay_linear(ts_delta(implied_volatility_call_60,25) - ts_delta(implied_volatility_put_60,25), 25), industry) - 0.5, 2)",
     S(0, 0.01)),
    ("f1_v5_amp3",
     "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25) - ts_delta(implied_volatility_put_60,25), 25)), 3)",
     S(0, 0.01)),
    ("f1_v6_sub_t05",
     "signed_power(zscore(ts_decay_linear(ts_delta(implied_volatility_call_60,25) - ts_delta(implied_volatility_put_60,25), 25)), 2)",
     S(4, 0.05, "SUBINDUSTRY")),
    ("f1_v7_dual_tenor",
     "signed_power(zscore(ts_decay_linear(0.5*(ts_delta(implied_volatility_call_60,25) - ts_delta(implied_volatility_put_60,25)) + 0.5*(ts_delta(implied_volatility_call_30,25) - ts_delta(implied_volatility_put_30,25)), 25)), 2)",
     S(4, 0.05, "SUBINDUSTRY")),

    # ===== FACTOR 2: social buzz fade =====
    ("f2_v0_orig",
     f"-ts_backfill(vec_sum({BUZZ_VEC}), 20)",
     S(5, 0.01)),
    ("f2_v1_grouprank",
     f"-group_rank(ts_backfill(vec_sum({BUZZ_VEC}), 20), industry)",
     S(5, 0.01)),
    ("f2_v2_smooth",
     f"-group_rank(ts_mean(ts_backfill(vec_sum({BUZZ_VEC}), 60), 20), industry)",
     S(5, 0.05)),
    ("f2_v3_matrix_buzz",
     f"-group_rank(ts_mean(ts_backfill({SCL_BUZZ_M}, 60), 20), industry)",
     S(5, 0.05)),
    ("f2_v4_buzz_x_sent",
     f"-group_rank(ts_mean(ts_backfill({SCL_BUZZ_M}, 60), 20), industry) + 0.5*group_rank(ts_mean(ts_backfill({SCL_SENT},60),20), industry)",
     S(5, 0.05)),
    ("f2_v5_buzz_x_qcm",
     f"-group_rank(ts_mean(ts_backfill({SCL_BUZZ_M}, 60), 20), industry) - 0.5*group_rank(ts_mean(ts_backfill({QCM},60),20), industry)",
     S(5, 0.05)),
]

def wname(r):
    return [c.get("name") for c in getattr(r, "checks", []) if c.get("result") == "FAIL"]

def robust(sess, fam, expr, s):
    r = None
    for attempt in range(6):
        try:
            r = submit(sess, fam, expr, s)
            if (not r.ok) and r.error and ("CONCURRENT" in str(r.error) or "429" in str(r.error)):
                log.info(f"   concurrent wait 60s ({attempt+1}/6)")
                time.sleep(60); continue
            return r
        except Exception as e:
            log.warning(f"   net {attempt+1}/6 {str(e)[:55]}")
            time.sleep(25)
    return r

def main():
    cm = _load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        return 2
    log.info(f"auth {cm.credentials.username}  OPTIMIZE TWO USER FACTORS (delay=1)")
    out = REPO/"WQ_OPT_TWO.json"
    res = []
    for i,(fam,expr,st) in enumerate(C, 1):
        s = dict(st); s["delay"] = 1; s.setdefault("universe","TOP3000")
        log.info(f"=== opt [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr[:140]}")
        r = robust(cm.session, fam, expr, s)
        if r is None: continue
        if r.ok:
            try:
                sc,_,_ = fetch_self_corr(cm.session, r.alpha_id, timeout_s=90)
                r.self_corr = sc
            except Exception:
                r.self_corr = None
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} sc={r.self_corr} FAIL={wname(r)}")
        else:
            log.warning(f"   FAILED: {str(r.error)[:130]}")
        res.append(r)
        json.dump([asdict(x) for x in res], open(out,"w"), indent=2)

    def ok_(r):
        return (r.ok and not wname(r)
                and (r.self_corr is None or abs(r.self_corr) < 0.7)
                and r.sharpe > 1.25)
    oks = sorted([r for r in res if r.ok], key=lambda r: r.sharpe, reverse=True)
    print("\n" + "="*110)
    print(f"OPT TWO: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc = f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        tag = "*** SUBMIT ***" if ok_(r) else ""
        print(f"  {r.family:<22} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {tag} {r.alpha_id}")
    for r in [r for r in res if not r.ok]:
        print(f"  FAIL {r.family}: {str(r.error)[:80]}")
    print("="*110)
    log.info(f"wrote {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
