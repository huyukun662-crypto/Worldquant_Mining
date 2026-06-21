"""Stage 1d: Family C — yet another structurally-distinct curated D1 set.

Distinct from Family A (price-volume corr + short reversal) and Family B
(VWAP / Amihud / gap / issuance / long-reversal / turnover). These probe
mean-reversion z-scores, acceleration, trend/MA-crossover, range dynamics,
intraday close position, and dollar-volume trend.

PV + slow fundamentals only; NO implied-volatility/option fields; no
ts_min/ts_max/ts_regression (inaccessible on this account tier). Delay=1.

Usage:  python scripts/mine_d1_v4.py
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mine-d1-v4")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

_spec = importlib.util.spec_from_file_location("mine_d1", REPO / "scripts" / "mine_d1.py")
mine_d1 = importlib.util.module_from_spec(_spec); sys.modules["mine_d1"] = mine_d1
_spec.loader.exec_module(mine_d1)

CANDIDATES = [
    # price z-score mean reversion
    ("Z_pricez_60",   "rank(divide(subtract(close, ts_mean(close, 60)), ts_std_dev(close, 60)))"),
    # second-order momentum (acceleration)
    ("ACC_close_20",  "rank(ts_delta(ts_delta(close, 20), 20))"),
    # volume z-score (abnormal volume)
    ("VZ_vol_60",     "rank(ts_zscore(volume, 60))"),
    # range trend (expanding/contracting daily range)
    ("RNG_trend_40",  "rank(ts_delta(divide(subtract(high, low), close), 40))"),
    # MA crossover trend filter (fast MA vs slow MA)
    ("MA_cross",      "rank(divide(ts_mean(close, 20), ts_mean(close, 120)))"),
    # cross-time reversal via ts_rank of returns
    ("TR_ret_60",     "rank(ts_rank(returns, 60))"),
    # intraday close position within the day's range, smoothed
    ("CP_pos_20",     "rank(ts_mean(divide(subtract(close, low), subtract(high, low)), 20))"),
    # dollar-volume trend (liquidity momentum)
    ("DV_trend_60",   "rank(ts_delta(ts_mean(multiply(close, volume), 20), 60))"),
    # vwap-close spread momentum
    ("VC_spread_20",  "rank(ts_delta(subtract(vwap, close), 20))"),
    # smoothed return autocorrelation proxy via av_diff
    ("AD_close_60",   "rank(ts_av_diff(close, 60))"),
]

BASE = {"universe": "TOP3000", "neutralization": "SUBINDUSTRY",
        "truncation": 0.08, "decay": 6}


def main():
    cm = mine_d1._load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
        base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    results = []
    for i, (name, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== [{i}/{len(CANDIDATES)}] {name}: {expr}")
        r = mine_d1.submit(cm.session, expr, BASE)
        rd = asdict(r); rd["name"] = name
        results.append(rd)
        if r.ok:
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                     f"DD={r.drawdown:.3f} sub={r.submittable} fail={r.failed_checks}")
        else:
            log.info(f"   [{r.error[:90]}]")
        json.dump(results, open(REPO / "WQ_D1_V4_REPORT.json", "w"), indent=2)
        time.sleep(2)

    ok = [r for r in results if r["ok"]]
    ok.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    print("\n" + "=" * 90)
    for r in ok:
        print(f"{r['sharpe']:+6.2f} TO={r['turnover']:.3f} DD={r['drawdown']:.3f} "
              f"sub={r['submittable']}  {r['name']:14} {r['expression'][:42]}")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
