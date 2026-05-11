"""QuantML round 14: aggressive R10_04 retune + 4 brand-new shapes.

R10_04 (intraday-body skew, 60d) hit SH=1.07 on TOP3000/MARKET/d4/
t0.08 -- the closest non-viable. R14_01 tries SUBINDUSTRY + decay=16
+ tighter truncation, which empirically is what pushed R6_01 over
the line.

The other four are shapes not yet tested across 100+ submissions:

  R14_02  cumulative downside return     ts_sum(min(returns,0),100)
  R14_03  rolling-beta time variation     std of rolling 60d beta
  R14_04  close anchor vs vwap anchor     mean(close,60)/mean(vwap,60)
  R14_05  short / long momentum velocity   21d ret / 252d ret ratio
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R14_01",
        "category": "body-skew-aggressive",
        "idea": (
            "R10_04 intraday-body-skew at SH=1.07. Aggressive retune: "
            "SUBINDUSTRY-neut + decay=16 + tight 0.04 truncation. "
            "These settings pushed R4_02-like shapes from 0.94 -> 1.51 "
            "in earlier rounds."
        ),
        "original": "R10_04 setting variant",
        "expression": (
            "-1 * ts_mean(power(ts_zscore("
            "(close - open) / open, 60), 3), 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 16,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.04,
        },
    },
    {
        "id": "QM_R14_02",
        "category": "cum-downside-return",
        "idea": (
            "Cumulative downside-only return over 100 days = "
            "sum of min(returns, 0). Captures actual crash exposure "
            "(integrated loss), distinct from STD of downside which "
            "captures variability. Long names with large negative "
            "cumulative crashes (mean reversion of distressed)."
        ),
        "original": "Sum(Min(Ret,0), 100)",
        "expression": "ts_sum(min(returns, 0), 100)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R14_03",
        "category": "beta-time-variation",
        "idea": (
            "Std of the rolling 60-day beta (from "
            "ts_regression(returns, market_mean_return, 60, "
            "rettype=2)) computed over a 60d outer window. "
            "Captures beta INSTABILITY. Short unstable-beta "
            "names."
        ),
        "original": "-Std(Slope(Ret,MktRet,60), 60)",
        "expression": (
            "-1 * ts_std_dev(ts_regression(returns, "
            "group_mean(returns, 1, market), 60, rettype=2), 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R14_04",
        "category": "close-vwap-anchor-ratio",
        "idea": (
            "60d mean(close) / 60d mean(vwap). Persistent close-"
            "above-vwap (>1) = end-of-day buying pressure dominates. "
            "Long names where institutional close-buying exceeds "
            "intraday vwap baseline."
        ),
        "original": "Mean(Close,60) / Mean(Vwap,60)",
        "expression": "ts_mean(close, 60) / ts_mean(vwap, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R14_05",
        "category": "momentum-velocity-ratio",
        "idea": (
            "Ratio of 21-day return to 252-day return. Long names "
            "whose short-term return EXCEEDS their long-term return "
            "pace (acceleration). Distinct shape from R2_03's "
            "DIFFERENCE form."
        ),
        "original": "Ret21 / Ret252",
        "expression": (
            "(close / ts_delay(close, 21) - 1) "
            "/ (close / ts_delay(close, 252) - 1)"
        ),
        "settings_override": {
            "universe": "TOP3000",
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
