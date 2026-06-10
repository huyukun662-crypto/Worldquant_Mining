"""Round 2: lift FIT, cut TO and drawdown without crashing SH.

v0 baseline: SH 1.99 / FIT 1.05 / TO 0.413 / sc 0.31 (ALREADY submittable).
Math: FIT = SH * sqrt(returns / max(TO, 0.125)). Cutting TO 0.41 -> 0.20
should lift FIT to ~1.5. But v4 (decay=8) killed SH (1.99 -> 1.12), so
heavy outer decay is wrong. Try gentler TO-cutters:
 - light outer smoothing (ts_mean 3-5)
 - longer ts_regression window (10 -> 15, 20)
 - longer ts_backfill window (30 -> 60)
 - tighter trade_when gate (fewer trade days)
 - pair with low-vol / quality (lowers drawdown)
delay=1.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

# Original signal pieces
def reg(win=10, bf=30):
    return f"rank(-1 * ts_regression(close, ts_backfill(call_breakeven_20, {bf}), {win}, rettype = 0))"

V0_SIG = reg(10, 30)
LOWVOL = "-group_rank(ts_std_dev(returns,60), market)"   # low-vol anomaly: helps drawdown
GP = "group_rank(divide(ts_backfill(sales,250), ts_backfill(assets,250)), market)"

def S(dec=2, tr=0.05, nt="MARKET"):
    return {"decay": dec, "truncation": tr, "neutralization": nt}

C = [
    # ===== light outer smoothing (cut TO without crushing SH) =====
    ("w1_tsmean3",        f"trade_when(pcr_oi_20 < 1, ts_mean({V0_SIG}, 3), -1)",   S(2, 0.05, "MARKET")),
    ("w2_tsmean5",        f"trade_when(pcr_oi_20 < 1, ts_mean({V0_SIG}, 5), -1)",   S(2, 0.05, "MARKET")),
    ("w3_decay3",         f"trade_when(pcr_oi_20 < 1, ts_decay_linear({V0_SIG}, 3), -1)", S(2, 0.05, "MARKET")),
    ("w4_decay5",         f"trade_when(pcr_oi_20 < 1, ts_decay_linear({V0_SIG}, 5), -1)", S(2, 0.05, "MARKET")),

    # ===== longer regression window (more stable signal) =====
    ("w5_reg15",          f"trade_when(pcr_oi_20 < 1, {reg(15, 30)}, -1)",          S(2, 0.05, "MARKET")),
    ("w6_reg20",          f"trade_when(pcr_oi_20 < 1, {reg(20, 30)}, -1)",          S(2, 0.05, "MARKET")),

    # ===== longer backfill window (smoother input) =====
    ("w7_bf60",           f"trade_when(pcr_oi_20 < 1, {reg(10, 60)}, -1)",          S(2, 0.05, "MARKET")),
    ("w8_reg15_bf60",     f"trade_when(pcr_oi_20 < 1, {reg(15, 60)}, -1)",          S(2, 0.05, "MARKET")),

    # ===== tighter trade_when gate (fewer trade days = lower TO) =====
    ("w9_gate08",         f"trade_when(pcr_oi_20 < 0.8, {V0_SIG}, -1)",             S(2, 0.05, "MARKET")),
    ("w10_gate08_reg15",  f"trade_when(pcr_oi_20 < 0.8, {reg(15, 30)}, -1)",        S(2, 0.05, "MARKET")),

    # ===== combine with low-vol (cuts drawdown) =====
    ("w11_v0_lowvol",     f"0.7 * (trade_when(pcr_oi_20 < 1, {V0_SIG}, -1)) + 0.3 * ({LOWVOL})", S(2, 0.05, "MARKET")),
    # ===== combine with gross-profitability (quality, lowers drawdown) =====
    ("w12_v0_gp",         f"0.7 * (trade_when(pcr_oi_20 < 1, {V0_SIG}, -1)) + 0.3 * ({GP})",      S(2, 0.05, "MARKET")),

    # ===== composite: smooth + tight gate + low-vol =====
    ("w13_smooth_tight_lowvol", f"0.7 * (trade_when(pcr_oi_20 < 0.8, ts_mean({V0_SIG}, 3), -1)) + 0.3 * ({LOWVOL})", S(2, 0.05, "MARKET")),
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
    log.info(f"auth {cm.credentials.username}  OPT3 R2 (lift FIT, cut TO, cut drawdown)")
    out=REPO/"WQ_OPT_THREE2.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== w [{i}/{len(C)}] {fam} ===")
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
        return (r.ok and not wname(r)
                and (r.self_corr is None or abs(r.self_corr)<0.7)
                and r.sharpe>1.25)
    oks=sorted([r for r in res if r.ok], key=lambda r: r.fitness, reverse=True)
    print("\n"+"="*110)
    print(f"OPT3 R2 (target: lift FIT > 1.05, lower TO < 0.41): submittable={sum(1 for r in oks if ok_(r))}/{len(oks)}")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        tag="*** SUBMIT ***" if ok_(r) else ""
        print(f"  {r.family:<24} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {tag} {r.alpha_id}")
    for r in [r for r in res if not r.ok]:
        print(f"  FAIL {r.family}: {str(r.error)[:90]}")
    print("="*110)
    log.info(f"wrote {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
