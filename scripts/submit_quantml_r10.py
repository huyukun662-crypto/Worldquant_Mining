"""QuantML round 10: peer-relative / cross-stock excess structures.

After 9 rounds the working shape families are:
  family A  asym-variance on price channel    (R6_01, OA24)
  family B  session-mean decomposition         (R8_03)

R10 hunts a third independent family: PEER-RELATIVE excess returns.
The signal lives in the difference between a stock and its group
average, not in its own time-series moments. Expected low
correlation with both A and B.

  R10_01  peer-relative 60d mean return       cross-sectional drift
  R10_02  peer-relative 60d return std         cross-sectional dispersion
  R10_03  vol-managed return                   vol-scaled return mean
  R10_04  realized-skew of intraday body       skew of (C-O)/O 60d
  R10_05  long-horizon mean reversal           1y vs current price
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R10_01",
        "category": "peer-rel-mean",
        "idea": (
            "60-day mean of (returns - subindustry mean returns). "
            "Cumulative outperformance vs peers. Long names ahead "
            "of group (continuation premium at horizons longer "
            "than INDUSTRY-neut residualizes)."
        ),
        "original": "Mean(Ret - GroupMean(Ret, SubInd), 60)",
        "expression": (
            "ts_mean(returns - group_mean(returns, 1, subindustry), 60)"
        ),
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R10_02",
        "category": "peer-rel-std",
        "idea": (
            "60-day std of (returns - subindustry mean returns). "
            "Cross-sectional idiosyncratic variance after peer "
            "subtraction. Sign: negative (idio-vol anomaly)."
        ),
        "original": "-Std(Ret - GroupMean(Ret, SubInd), 60)",
        "expression": (
            "-1 * ts_std_dev("
            "returns - group_mean(returns, 1, subindustry), 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R10_03",
        "category": "vol-managed-return",
        "idea": (
            "60d mean of returns divided by 20d lagged vol -- vol-"
            "scaled returns. Volatility-managed strategies have a "
            "well-documented SH premium; structurally a normalised "
            "mean (not a variance asym, not a session diff)."
        ),
        "original": "Mean(Ret / Delay(Std(Ret,20), 1), 60)",
        "expression": (
            "ts_mean(returns / ts_delay(ts_std_dev(returns, 20), 1), 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R10_04",
        "category": "intraday-body-skew",
        "idea": (
            "60d skewness of intraday body (close-open)/open. "
            "Body distribution is a separate object from return "
            "distribution; its skew encodes intraday selling-"
            "pressure asymmetry. Short positive-skew names."
        ),
        "original": "-Skew((C-O)/O, 60)",
        "expression": (
            "-1 * ts_mean(power(ts_zscore("
            "(close - open) / open, 60), 3), 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "MARKET",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R10_05",
        "category": "annual-mean-reversion",
        "idea": (
            "Long-horizon mean reversion: 252-day mean(close)/close "
            "minus 21-day mean(close)/close. Long names trading "
            "below their annual mean but above their monthly mean "
            "(end of correction). Different time scale from R1_02."
        ),
        "original": "Mean(C,252)/C - Mean(C,21)/C",
        "expression": (
            "ts_mean(close, 252) / close "
            "- ts_mean(close, 21) / close"
        ),
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
]


if __name__ == "__main__":
    sys.exit(
        run_round(
            FACTORS,
            results_path=Path(__file__).resolve().parent.parent
            / "WQ_QUANTML_RESULTS.json",
            append=True,
        )
    )
