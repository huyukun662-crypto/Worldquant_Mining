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
              "F_0m7QR858": "0m7QR858"}
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

CANDIDATES = [
    # Closest near-miss intra_amih_d12 SH=1.23/FIT=0.97. Add 1 more driver and try
    # lower decay (less signal degradation) + winsorize wrappers (clean tails -> fit)
    ("intra_am_vc",     blend(*INTRADAY7, "amihud", "vcspread"),  {**BASE, "universe": "TOP3000", "neutralization": "SUBINDUSTRY", "decay": 10}),
    ("intra_am_iss",    blend(*INTRADAY7, "amihud", "issuance"),  {**BASE, "universe": "TOP3000", "neutralization": "SUBINDUSTRY", "decay": 10}),
    ("intra_am_tov",    blend(*INTRADAY7, "amihud", "turnover"),  {**BASE, "universe": "TOP3000", "neutralization": "SUBINDUSTRY", "decay": 10}),
    ("intra_amih_d8",   blend(*INTRADAY7, "amihud"),              {**BASE, "universe": "TOP3000", "neutralization": "SUBINDUSTRY", "decay": 8}),
    ("intra_amih_d10",  blend(*INTRADAY7, "amihud"),              {**BASE, "universe": "TOP3000", "neutralization": "SUBINDUSTRY", "decay": 10}),
    # Winsorized wrappers (clean tails -> higher fitness)
    ("intra_am_win_d10", "rank(winsorize(" + blend(*INTRADAY7, "amihud")[5:-1] + ", std=4))",
                                                                  {**BASE, "universe": "TOP3000", "neutralization": "SUBINDUSTRY", "decay": 10}),
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
            if r.submittable:
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
        json.dump(results, open(REPO / "WQ_D1_LOWCORR_REPORT13.json", "w"), indent=2)
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
