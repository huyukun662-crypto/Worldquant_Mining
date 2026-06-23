"""Stage: mine SUBMITTABLE D1 alphas that are LOW-CORRELATED with the
previously found winners (Family A 58w3aOKM, Family B 58w9r6E6).

For each candidate it (1) simulates on WQ Brain delay=1, (2) if the alpha
passes every deterministic IS check, fetches its daily PnL and computes the
Pearson correlation of daily PnL against each reference alpha, (3) reports
candidates that are both submittable AND low-correlation.

Daily PnL is the WQ `/alphas/{id}/recordsets/pnl` cumulative series,
first-differenced to daily PnL before correlating.

Usage:  python scripts/mine_lowcorr.py
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lowcorr")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

_spec = importlib.util.spec_from_file_location("mine_d1", REPO / "scripts" / "mine_d1.py")
mine_d1 = importlib.util.module_from_spec(_spec); sys.modules["mine_d1"] = mine_d1
_spec.loader.exec_module(mine_d1)

REFERENCES = {"A_58w3aOKM": "58w3aOKM", "B_58w9r6E6": "58w9r6E6",
              "D_88z6bZEq": "88z6bZEq", "E_d5x78JRv": "d5x78JRv",
              "F_0m7QR858": "0m7QR858", "G_LLpgPEja": "LLpgPEja",
              "H_78wa9R3Q": "78wa9R3Q"}
CORR_CEILING = 0.50          # "low correlation" target

BASE = {"truncation": 0.08}

A_EXPR = ("rank(winsorize(add(rank(-ts_corr(close, volume, 20)), "
          "rank(divide(-ts_delta(close, 10), ts_std_dev(returns, 10)))), std=4))")

# Sign-corrected component building blocks (directed so each has +Sharpe).
C = {
    "pvcorr":   "rank(-ts_corr(close, volume, 20))",                                      # price-volume divergence
    "trret":    "-rank(ts_rank(returns, 60))",                                            # 60d rank reversal
    "vcspread": "rank(ts_delta(subtract(vwap, close), 20))",                              # vwap-close spread mom
    "pricez":   "-rank(divide(subtract(close, ts_mean(close, 60)), ts_std_dev(close, 60)))",  # price z reversal
    "avdiff":   "-rank(ts_av_diff(close, 60))",                                           # av_diff reversal
    "cppos":    "-rank(ts_mean(divide(subtract(close, low), subtract(high, low)), 20))",  # close position
    "amihud":   "-rank(ts_mean(divide(abs(returns), multiply(close, volume)), 60))",      # illiquidity
    "issuance": "-rank(ts_delta(sharesout, 120))",                                        # net issuance
    "turnover": "rank(ts_mean(divide(volume, sharesout), 60))",                           # share turnover
    "volz":     "rank(ts_zscore(volume, 60))",                                            # abnormal volume
    "rngtrend": "rank(ts_delta(divide(subtract(high, low), close), 40))",                 # range trend
    "gap":      "rank(ts_mean(divide(open, ts_delay(close, 1)), 20))",                    # overnight-gap reversal
}


def blend(*keys: str) -> str:
    parts = [C[k] for k in keys]
    e = parts[0]
    for p in parts[1:]:
        e = f"add({e}, {p})"
    return f"rank({e})"


# Candidates designed to lean on DIFFERENT drivers than A/B (which are
# pv-corr + short vol-normalized reversal, and the 6-idea liquidity blend).
# NEW HORIZON axis: blends that the existing factors don't span.
# All TOP3000 (the only universe where SH>1.25 is reachable).
C["vwap_pos"]   = "-rank(ts_mean(divide(close, vwap), 10))"
C["cppos40"]    = "-rank(ts_mean(divide(subtract(close, low), subtract(high, low)), 40))"
C["rng40"]      = "rank(ts_delta(divide(subtract(high, low), close), 40))"
C["rng60"]      = "rank(ts_delta(divide(subtract(high, low), close), 60))"
C["vwap40"]     = "-rank(ts_mean(divide(close, vwap), 40))"
C["vwap_disp"]  = "-rank(ts_std_dev(divide(close, vwap), 40))"
C["lowvol120"]  = "rank(ts_std_dev(returns, 120))"  # low-vol anomaly: low vol = high return
C["mom240"]     = "rank(ts_delta(close, 240))"      # very-long momentum
C["adv_ratio"]  = "rank(divide(volume, ts_mean(volume, 240)))"  # 240d volume ratio
C["gap60"]      = "rank(ts_mean(divide(open, ts_delay(close, 1)), 60))"
C["volstd_z"]   = "-rank(ts_zscore(ts_std_dev(returns, 20), 120))"  # vol regime z-score (low vol)

INTRADAY7 = ("cppos", "cppos40", "rng40", "rng60", "vwap_pos", "vwap40", "vwap_disp")

EREC = ("trret", "amihud", "turnover", "volz", "gap")  # E / mixbal recipe

PVCEREC = ("pvcorr",) + EREC  # the SH 1.54 winning recipe (pvcorr + E recipe)

# ---------------------------------------------------------------------------
# BATCH 20: a GENUINELY NEW driver axis. Families A-H are all pure
# price-volume (reversal / flow / microstructure). To escape the structural
# wall (every strong P-V reversal+flow blend correlates >=0.5 with E), pull in
# FUNDAMENTAL value/quality/growth + long-horizon momentum + low-vol anomaly.
# All fields are delay=1 fundamentals (no IV/option), confirmed present on
# USA TOP3000 delay=1. These are economically orthogonal to technical signals.
# ---------------------------------------------------------------------------
# Value (cheapness): high ratio => cheap => long.  cap = price*sharesout.
C["val_ey"]   = "rank(divide(operating_income, cap))"          # earnings yield
C["val_bp"]   = "rank(divide(equity, cap))"                    # book-to-price
C["val_cfp"]  = "rank(divide(cashflow_op, cap))"               # cashflow yield
C["val_sp"]   = "rank(divide(sales, cap))"                     # sales-to-price
# Quality: profitability high => long; leverage high => short.
C["q_gp"]     = "rank(divide(operating_income, assets))"       # gross profitability (Novy-Marx)
C["q_roe"]    = "rank(divide(operating_income, equity))"       # return on equity
C["q_lev"]    = "-rank(divide(debt, equity))"                  # low leverage
C["q_accr"]   = "rank(divide(subtract(cashflow_op, operating_income), assets))"  # low accruals (cash earnings quality)
# Growth.
C["g_sales"]  = "rank(sales_growth)"                           # sales growth
# Long-horizon momentum (12-1) and low-vol anomaly — technical but a driver
# the short-reversal families do NOT span.
C["mom121"]   = "rank(divide(ts_delay(close, 21), ts_delay(close, 252)))"   # 12m-minus-1m momentum
C["lowvol"]   = "-rank(ts_std_dev(returns, 120))"             # low-volatility anomaly

T3 = "TOP3000"

# ---------------------------------------------------------------------------
# BATCH 21: analyst-revision / sentiment / news / short-interest axis.
# Batch 20 proved slow fundamentals + long-mom/low-vol can't reach SH 1.25 on
# this tier. These delay=1 fields are documented standalone alpha sources
# (post-earnings/analyst drift, sentiment, crowded-short) and are economically
# orthogonal to BOTH the price-volume families (A-H) AND slow fundamentals.
# Sign convention: upward revisions / target upside / positive sentiment = LONG;
# high short interest / days-to-cover = SHORT.
# ---------------------------------------------------------------------------
C["rev_fy1"]   = "rank(net_num_revisions_fy1)"                 # net up-minus-down FY1 revisions
C["rev_fy2"]   = "rank(net_num_revisions_fy2)"                 # net FY2 revisions
C["rev_mag"]   = "rank(earnings_revision_magnitude)"          # size of revisions
C["rev_rankd"] = "rank(analyst_revision_rank_derivative)"     # revision-rank momentum
C["ptp_up"]    = "rank(divide(anl4_ptp_mean, close))"        # mean price-target upside
C["snt_soc"]   = "rank(snt_social_value)"                     # signed social sentiment
C["news_snt"]  = "rank(ts_mean(news_ls, 20))"                 # news long-short signal
C["si_short"]  = "-rank(mdl177_5shortsentimentfactor_sht_int)"          # crowded-short -> short
C["dtc_short"] = "-rank(mdl177_5shortsentimentfactor_days_to_cover)"    # days-to-cover -> short

CANDIDATES = []

# ---------------------------------------------------------------------------
# BATCH 22: STRONG price-volume base + weak ORTHOGONAL tilt.
# pvcerec (pvcorr + E-recipe) on TOP1000/SUBIND/decay18 = SH 1.54 but corr 0.58
# with E (shares E's reversal/flow recipe). Batches 20-21 showed value/quality
# and analyst signals are ~0 corr with E but too weak standalone. So ADD a small
# weighted value/quality/target tilt to the strong base: the tilt rotates the
# combined factor away from E's direction (pushing corr <0.5) while the P-V base
# keeps Sharpe high. Sweep tilt TYPE x WEIGHT to find SH>1.25 AND corr_E<0.5.
# ---------------------------------------------------------------------------
PVC_BASE = blend(*PVCEREC)                       # rank in [0,1], SH 1.54 base
TILT = {
    "val":  blend("val_cfp", "val_ey"),          # cashflow + earnings yield (value)
    "gp":   "rank(divide(operating_income, assets))",   # gross profitability (quality)
    "ptp":  "rank(divide(anl4_ptp_mean, close))",       # analyst target upside
    "vq":   blend("val_cfp", "q_gp"),            # value + quality composite
}
def tilted(tkey: str, w: float) -> str:
    return f"rank(add({PVC_BASE}, multiply({w}, {TILT[tkey]})))"

H_SET = {**BASE, "universe": "TOP1000", "neutralization": "SUBINDUSTRY", "decay": 18}

# BATCH 25: value tilt. Batch 24 confirmed corr_H is WEIGHT-driven (w050 -> 0.585
# at any decay) and decay only buys Sharpe. corr_H crosses 0.5 around w~0.60
# (w060/d18: SH 1.23, corr_H 0.484). So push weight to 0.58-0.64 to get corr_H<0.5
# AND use low decay (12/14) to lift SH back over 1.25. Predicted winner ~w062/d12:
# SH ~1.33, corr_H ~0.466. corr computed for every SH>1.0 alpha.
def tilted_d(tkey: str, w: float, decay: int):
    expr = f"rank(add({PVC_BASE}, multiply({w}, {TILT[tkey]})))"
    return (f"pvc_{tkey}_w{int(w*100):03d}_d{decay:02d}", expr,
            {**BASE, "universe": "TOP1000", "neutralization": "SUBINDUSTRY", "decay": decay})

# BATCH 26: ROBUSTNESS. Family I (pvc_val_w060_d14, N1pnoddo) passes but at the
# edge: corr_H=0.497 (its base IS H's exact pvcerec recipe, so the value tilt
# only rotated it away from E, not H). To win MARGIN (corr<0.47 AND SH>1.30) we
# must rotate the BASE away from H too. Two prongs:
#  (A) THINNED base: drop trret (the 60d reversal that drives the E/H overlap);
#      pvcorr+amihud+turnover+volz+gap is still strong but less H-like, then add
#      value tilt. Lower corr_H at a given weight -> room to keep SH up.
#  (B) NEUTRALIZATION rotation: H is SUBINDUSTRY; run the full base under INDUSTRY
#      / SECTOR so the whole vector is structurally decorrelated from H.
THIN = ("pvcorr", "amihud", "turnover", "volz", "gap")   # pvcerec minus trret
THIN_BASE = blend(*THIN)
def thin_val(w: float, decay: int, neut: str = "SUBINDUSTRY"):
    expr = f"rank(add({THIN_BASE}, multiply({w}, {TILT['val']})))"
    tag = {"SUBINDUSTRY": "sub", "INDUSTRY": "ind", "SECTOR": "sec"}[neut]
    return (f"thin_val_w{int(w*100):03d}_d{decay:02d}_{tag}", expr,
            {**BASE, "universe": "TOP1000", "neutralization": neut, "decay": decay})
def pvc_val_neut(w: float, decay: int, neut: str):
    expr = f"rank(add({PVC_BASE}, multiply({w}, {TILT['val']})))"
    tag = {"INDUSTRY": "ind", "SECTOR": "sec"}[neut]
    return (f"pvc_val_w{int(w*100):03d}_d{decay:02d}_{tag}", expr,
            {**BASE, "universe": "TOP1000", "neutralization": neut, "decay": decay})

# BATCH 27: exploit the now-open setting space (everything except region=USA).
# Batch 26 found the winning ROTATION: full pvcerec base + value tilt under
# INDUSTRY neut decorrelates from H (SUBINDUSTRY). The weight curve at INDUSTRY:
#   w045 -> corr_H 0.537 / SH 1.29   (corr too high)
#   w050 -> corr_H 0.492 / SH 1.23   (SH just short)
# corr_H is weight-driven; decay is a ~corr-neutral SH lever (batch 24). So pin
# w050 INDUSTRY (corr_H~0.49) and drop decay to lift SH>1.30. Plus two more
# orthogonalizers now permitted: UNIVERSE rotation (A-H live on TOP1000; TOP2000
# is structurally decorrelated) and truncation/pasteurization tweaks.
def pvc_val_full(w: float, decay: int, neut: str, universe: str = "TOP1000",
                 truncation: float = 0.08, pasteur: str = "ON"):
    expr = f"rank(add({PVC_BASE}, multiply({w}, {TILT['val']})))"
    ntag = {"SUBINDUSTRY": "sub", "INDUSTRY": "ind", "SECTOR": "sec"}[neut]
    utag = {"TOP1000": "t1k", "TOP2000": "t2k", "TOP3000": "t3k", "TOP500": "t05"}[universe]
    extra = (f"_{utag}" if universe != "TOP1000" else "") + \
            (f"_t{int(truncation*100):02d}" if truncation != 0.08 else "") + \
            ("_pOFF" if pasteur != "ON" else "")
    name = f"pvc_val_w{int(w*100):03d}_d{decay:02d}_{ntag}{extra}"
    st = {**BASE, "universe": universe, "neutralization": neut,
          "decay": decay, "truncation": truncation, "pasteurization": pasteur}
    return (name, expr, st)

# BATCH 28: D = blend(amihud, issuance, turnover, volz) on TOP3000. Our pvcerec
# base SHARES 3/4 of D's flow recipe (amihud, turnover, volz), so corr_D is
# weight-insensitive (value tilt rotates away from H's reversal+E, not from flow)
# and TOP2000/3000 INFLATE corr_D (D lives in the big universe). Conclusion:
# TOP1000 is the right universe for this base (corr_D ~0.39, only corr_H binds).
# On TOP1000 INDUSTRY, batch 27 showed w052_d08 -> corr_H 0.48 (already <0.5!) but
# FIT 0.97. Fix: raise decay to recover fitness (lower turnover) while keeping the
# w052+ weight that pushes corr_H <0.47. Sweep weight x decay on TOP1000 INDUSTRY.
for w in (0.52, 0.55, 0.58):
    for decay in (12, 14):
        CANDIDATES.append(pvc_val_full(w, decay, "INDUSTRY", universe="TOP1000"))
# Two confirmations: w055 at decay 10 (more SH) and w052 d14 already covered above.
CANDIDATES.append(pvc_val_full(0.55, 10, "INDUSTRY", universe="TOP1000"))
CANDIDATES.append(pvc_val_full(0.60, 12, "INDUSTRY", universe="TOP1000"))

_UNUSED_BATCH21 = [
]



def fetch_pnl(session, aid: str) -> dict:
    url = f"https://api.worldquantbrain.com/alphas/{aid}/recordsets/pnl"
    for _ in range(20):
        r = session.get(url, timeout=30)
        if r.status_code == 200 and r.text.strip():
            return {x[0]: x[1] for x in r.json()["records"]}
        time.sleep(2)
    return {}


def corr(a: dict, b: dict) -> float:
    dates = sorted(set(a) & set(b))
    if len(dates) < 50:
        return float("nan")
    x = np.diff(np.array([a[d] for d in dates], float))
    y = np.diff(np.array([b[d] for d in dates], float))
    if x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def main():
    cm = mine_d1._load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
        base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    ref_pnl = {name: fetch_pnl(cm.session, aid) for name, aid in REFERENCES.items()}
    for name, p in ref_pnl.items():
        log.info(f"reference {name}: {len(p)} pnl days")

    results = []
    for i, (name, expr, settings) in enumerate(CANDIDATES, 1):
        log.info(f"=== [{i}/{len(CANDIDATES)}] {name} neut={settings['neutralization']} decay={settings['decay']}")
        r = mine_d1.submit(cm.session, expr, settings)
        rec = {"name": name, "expression": expr, "settings": r.settings,
               "ok": r.ok, "sharpe": r.sharpe, "turnover": r.turnover,
               "fitness": r.fitness, "drawdown": r.drawdown,
               "submittable": r.submittable, "failed_checks": r.failed_checks,
               "alpha_id": r.alpha_id, "error": r.error, "corr": {}}
        if r.ok:
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                     f"DD={r.drawdown:.3f} sub={r.submittable} fail={r.failed_checks}")
            # Compute corr for any decent-Sharpe alpha (not just submittable) so
            # we can map the SH-vs-corr_E tradeoff of the tilt-weight sweep.
            if r.alpha_id and r.sharpe is not None and r.sharpe > 1.0:
                cp = fetch_pnl(cm.session, r.alpha_id)
                for rn, rp in ref_pnl.items():
                    rec["corr"][rn] = round(corr(cp, rp), 3)
                mx = max((abs(v) for v in rec["corr"].values()), default=float("nan"))
                rec["max_abs_corr"] = round(mx, 3)
                log.info(f"   CORR {rec['corr']}  max|corr|={mx:.3f}  "
                         f"{'LOW-CORR ✔' if mx < CORR_CEILING else 'too correlated'}")
        else:
            log.info(f"   [{r.error[:80]}]")
        results.append(rec)
        json.dump(results, open(REPO / "WQ_D1_LOWCORR_REPORT28.json", "w"), indent=2)
        time.sleep(2)

    winners = [r for r in results if r.get("submittable") and r["sharpe"] > 1.25
               and r["turnover"] < 0.25 and r.get("max_abs_corr", 1) < CORR_CEILING]
    winners.sort(key=lambda r: r["max_abs_corr"])
    print("\n" + "=" * 100)
    print(f"SUBMITTABLE + LOW-CORR (<{CORR_CEILING}) winners: {len(winners)}")
    for r in winners:
        print(f"  {r['name']:18} SH={r['sharpe']:.3f} TO={r['turnover']:.3f} "
              f"DD={r['drawdown']:.3f} corr={r['corr']} id={r['alpha_id']}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
