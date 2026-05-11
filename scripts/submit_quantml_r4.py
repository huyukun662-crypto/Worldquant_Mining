"""QuantML round 4: push SH past 1.25.

Lessons from rounds 1-3:
- Single-shape statistics (skew/kurt/idio-vol/vol-of-vol/lottery)
  cap at SH≈0.55-0.85 after INDUSTRY-neut + 0.08 truncation.
- The OpenAlpha winner OA24 (SH=1.47) used HIGH/LOW vs prior close,
  not pure returns -- the OHLC channel adds genuinely different
  information from close-to-close returns.
- Rank-averaging composites (R3_05) DILUTED signal vs the underlying
  factors. Sum-of-signed-z-scores should preserve more.

Round 4 (five new structurally distinct factors):

  R4_01 OHLC pressure asymmetry (mean-based, distinct from OA24's std-based)
  R4_02 conditional downside vol via `less(returns, 0)`
  R4_03 overnight-gap accumulated 20d
  R4_04 sum-composite of three orthogonal shape statistics (z-scored)
  R4_05 normalised distance from 60d mean (Bollinger-z without bands)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R4_01",
        "category": "ohlc-pressure",
        "idea": (
            "Mean upper-shadow ((high-close)/close) minus mean lower-"
            "shadow ((close-low)/close) over 60d. Negative when sellers "
            "press the close near the low repeatedly -> short these. "
            "Distinct from OA24 which is std-based on prior-close-"
            "normalised ranges."
        ),
        "original": "Mean((H-C)/C, 60) - Mean((C-L)/C, 60)",
        "expression": (
            "ts_mean((high - close) / close, 60) "
            "- ts_mean((close - low) / close, 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R4_02",
        "category": "conditional-downvol",
        "idea": (
            "Pure-downside semi-deviation using `less(returns, 0)` "
            "mask (= 1 on down days, 0 on up days). Long names with "
            "high downside variance (risk premium); short symmetric."
        ),
        "original": "Std(Ret * I(Ret<0), 100)",
        "expression": (
            "ts_std_dev(returns * less(returns, 0), 100) "
            "- ts_std_dev(returns * greater(returns, 0), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R4_03",
        "category": "overnight-gap",
        "idea": (
            "Accumulated 20-day overnight gap: open relative to "
            "previous close. Persistent positive gap = "
            "institutional bid -> long. SUBINDUSTRY-neut since "
            "gaps cluster by industry news cycles."
        ),
        "original": "Mean(Open/Delay(Close,1) - 1, 20)",
        "expression": "ts_mean(open / ts_delay(close, 1) - 1, 20)",
        "settings_override": {
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R4_04",
        "category": "z-sum-composite",
        "idea": (
            "Sum of cross-sectional z-scores of the three "
            "orthogonal best singletons: kurtosis, third-moment, "
            "return-vol coupling. ZSum preserves direction vs rank-"
            "averaging which dilutes. Hopes that uncorrelated weak "
            "signals add to a stronger one."
        ),
        "original": "Z(NegKurt) + Z(NegSkew) + Z(NegRetVolCoup)",
        "expression": (
            "ts_zscore("
            "-1 * ts_mean(power(ts_zscore(returns, 60), 4), 60), "
            "20) "
            "+ ts_zscore("
            "-1 * ts_mean(power(ts_zscore(returns, 60), 3), 60), "
            "20) "
            "+ ts_zscore("
            "-1 * ts_corr(returns, abs(returns), 60), "
            "20)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "MARKET",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R4_05",
        "category": "bollinger-z",
        "idea": (
            "Standardised distance from the 60-day mean "
            "(Bollinger-style z): (close - ts_mean) / ts_std_dev. "
            "Long names below their mean by ~2 sigma (mean reverts). "
            "Different from R1_02 in that it normalises by std, not "
            "by current price."
        ),
        "original": "(Close - Mean(Close,60)) / Std(Close,60)",
        "expression": (
            "-1 * (close - ts_mean(close, 60)) / ts_std_dev(close, 60)"
        ),
        "settings_override": {
            "decay": 0,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
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
