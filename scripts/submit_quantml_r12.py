"""QuantML round 12: setting-space exploration.

All 89 prior submissions used universe=TOP3000. Now that all
settings are tunable, the unused lever is universe size. Smaller
universes give more concentrated bets -- typically higher SH at
the cost of slightly higher TO.

R12 retries near-misses on smaller universes plus one new shape:

  R12_01  R4_02   asym-vol-on-returns      universe=TOP500, decay=8
  R12_02  R10_04  intraday-body-skew       universe=TOP500, decay=4
  R12_03  R6_03   upper-shadow-on-up       universe=TOP1000, decay=4
  R12_04  R8_03   session decomp           universe=TOP500 (test
                                            our winner on small uni)
  R12_05  NEW     100d overnight gap std    universe=TOP500, no neut

Expected: at least one of R12_01/R12_02/R12_03 crosses SH=1.35
when given a smaller universe to bet over.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


R4_02 = (
    "ts_std_dev(returns * less(returns, 0), 100) "
    "- ts_std_dev(returns * greater(returns, 0), 100)"
)
R10_04 = (
    "-1 * ts_mean(power(ts_zscore((close - open) / open, 60), 3), 60)"
)
R6_03 = (
    "-1 * ts_mean((high - close) / close * greater(close - open, 0), 60)"
)
R8_03 = (
    "ts_mean(open / ts_delay(close, 1) - 1, 60) "
    "- ts_mean(close / open - 1, 60)"
)
OVERNIGHT_STD = (
    "-1 * ts_std_dev(open / ts_delay(close, 1) - 1, 100)"
)


FACTORS: list[dict] = [
    {
        "id": "QM_R12_01",
        "category": "asym-vol-return-TOP500",
        "idea": (
            "R4_02 asym-variance on returns -- got SH=0.94 on TOP3000. "
            "Retry on TOP500 with decay=8 for concentration boost."
        ),
        "original": "R4_02 setting variant",
        "expression": R4_02,
        "settings_override": {
            "universe": "TOP500",
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R12_02",
        "category": "body-skew-TOP500",
        "idea": (
            "R10_04 intraday-body-skew (SH=1.07 on TOP3000). Try "
            "TOP500 + decay=4 to bridge the gap to SH=1.35."
        ),
        "original": "R10_04 setting variant",
        "expression": R10_04,
        "settings_override": {
            "universe": "TOP500",
            "decay": 4,
            "neutralization": "MARKET",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R12_03",
        "category": "upper-shadow-up-TOP1000",
        "idea": (
            "R6_03 upper-shadow-on-up (SH=0.85 FIT=1.04 on TOP3000). "
            "TOP1000 + decay=4 + tighter trunc to gain SH."
        ),
        "original": "R6_03 setting variant",
        "expression": R6_03,
        "settings_override": {
            "universe": "TOP1000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R12_04",
        "category": "session-decomp-TOP500",
        "idea": (
            "R8_03 session decomp -- check whether the winner "
            "generalises to TOP500. Validates the small-universe "
            "hypothesis."
        ),
        "original": "R8_03 setting variant",
        "expression": R8_03,
        "settings_override": {
            "universe": "TOP500",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R12_05",
        "category": "overnight-std-TOP500",
        "idea": (
            "100-day std of overnight gaps, no asymmetry, no neut. "
            "Pure variance signal: short names with high overnight-"
            "gap volatility (overnight risk premium)."
        ),
        "original": "Std(Open/Delay(Close,1) - 1, 100)",
        "expression": OVERNIGHT_STD,
        "settings_override": {
            "universe": "TOP500",
            "decay": 4,
            "neutralization": "NONE",
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
