"""Optimize the user's third factor (pcr_oi/call_breakeven trade_when) to submittable.

Original:
  trade_when(pcr_oi_20 < 1,
             rank(-1 * ts_regression(close, ts_backfill(call_breakeven_20, 30), 10, rettype=0)),
             -1)
Settings: TOP3000, delay=1, MARKET, decay=2, truncation=0.01, pasteurization=ON

Test v0 (faithful repro) first, then attack likely fails systematically.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

# Original signal (the "what trade when condition is true" part)
SIG = "rank(-1 * ts_regression(close, ts_backfill(call_breakeven_20, 30), 10, rettype = 0))"
# Gate variants
G_DEFAULT = "pcr_oi_20 < 1"
G_LOOSER  = "pcr_oi_20 < 1.2"
G_TIGHTER = "pcr_oi_20 < 0.8"

# Variants of inner signal (try different rettype for ts_regression)
def sig_rettype(rt): return f"rank(-1 * ts_regression(close, ts_backfill(call_breakeven_20, 30), 10, rettype = {rt}))"

def S(dec=2, tr=0.01, nt="MARKET"):
    return {"decay": dec, "truncation": tr, "neutralization": nt}

C = [
    # ===== v0: exact reproduction =====
    ("v0_original",       f"trade_when({G_DEFAULT}, {SIG}, -1)",       S(2, 0.01, "MARKET")),

    # ===== fix CONCENTRATED_WEIGHT (likely fail with trunc 0.01) =====
    ("v1_trunc05",        f"trade_when({G_DEFAULT}, {SIG}, -1)",       S(2, 0.05, "MARKET")),
    ("v2_trunc08",        f"trade_when({G_DEFAULT}, {SIG}, -1)",       S(2, 0.08, "MARKET")),
    ("v3_trunc10",        f"trade_when({G_DEFAULT}, {SIG}, -1)",       S(2, 0.10, "MARKET")),

    # ===== fix high turnover via decay =====
    ("v4_dec8_t05",       f"trade_when({G_DEFAULT}, {SIG}, -1)",       S(8, 0.05, "MARKET")),
    ("v5_dec12_t08",      f"trade_when({G_DEFAULT}, {SIG}, -1)",       S(12, 0.08, "MARKET")),

    # ===== alt neutralization =====
    ("v6_sub_t05",        f"trade_when({G_DEFAULT}, {SIG}, -1)",       S(2, 0.05, "SUBINDUSTRY")),
    ("v7_ind_t05",        f"trade_when({G_DEFAULT}, {SIG}, -1)",       S(2, 0.05, "INDUSTRY")),

    # ===== try different ts_regression rettype =====
    # rettype meanings vary; try 1, 2 (typically slope/intercept)
    ("v8_rettype1",       f"trade_when({G_DEFAULT}, {sig_rettype(1)}, -1)", S(4, 0.05, "MARKET")),
    ("v9_rettype2",       f"trade_when({G_DEFAULT}, {sig_rettype(2)}, -1)", S(4, 0.05, "MARKET")),

    # ===== gate variants =====
    ("v10_loose_gate",    f"trade_when({G_LOOSER}, {SIG}, -1)",        S(4, 0.05, "MARKET")),
    ("v11_tight_gate",    f"trade_when({G_TIGHTER}, {SIG}, -1)",       S(4, 0.05, "MARKET")),

    # ===== drop the trade_when gate entirely (no conditional) =====
    ("v12_no_gate",       f"{SIG}",                                     S(4, 0.05, "MARKET")),
    ("v13_no_gate_dec8",  f"{SIG}",                                     S(8, 0.05, "MARKET")),
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
    log.info(f"auth {cm.credentials.username}  OPT3 R1 (user factor #3: pcr_oi + call_breakeven)")
    out=REPO/"WQ_OPT_THREE.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== o3 [{i}/{len(C)}] {fam} ===")
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
    oks=sorted([r for r in res if r.ok], key=lambda r: r.sharpe, reverse=True)
    print("\n"+"="*110); print(f"OPT3: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        tag="*** SUBMIT ***" if ok_(r) else ""
        print(f"  {r.family:<22} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {tag} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:90]}")
    print("="*110); log.info(f"wrote {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
