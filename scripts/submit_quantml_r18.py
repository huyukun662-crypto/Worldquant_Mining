"""QuantML round 18: shadow-on-day-sign factors.

R6_03 (upper shadow on up days) hit SH=0.85 FIT=1.04 with default
settings. Never retuned with the winning recipe (IND d=4 t=0.05)
that lifted R10_04: 1.07 -> 1.20 -> 1.35 (R16_05).

Plus a mirror new shape: lower shadow on DOWN days (rejection of
lows, mean reversion).

  R18_01  R6_03 IND d=4 t=0.05         winning-recipe retune
  R18_02  R6_03 SUB d=4 t=0.05         sub-industry variant
  R18_03  R6_03 with window 100d        longer
  R18_04  NEW: lower-shadow-on-down 60d  mirror of R6_03
  R18_05  R4_02 IND d=4 t=0.05         conditional-downvol on returns
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

R6_03_60 = (
    "-1 * ts_mean((high - close) / close "
    "* greater(close - open, 0), 60)"
)
R6_03_100 = (
    "-1 * ts_mean((high - close) / close "
    "* greater(close - open, 0), 100)"
)
LOWER_SHADOW_DOWN = (
    "-1 * ts_mean((close - low) / close "
    "* less(close - open, 0), 60)"
)
R4_02 = (
    "ts_std_dev(returns * less(returns, 0), 100) "
    "- ts_std_dev(returns * greater(returns, 0), 100)"
)


FACTORS: list[dict] = [
    {
        "id": "QM_R18_01",
        "category": "upper-shadow-up-tuned",
        "idea": (
            "R6_03 upper-shadow-on-up retuned with the recipe that "
            "lifted R10_04: INDUSTRY d=4 trunc=0.05."
        ),
        "original": "R6_03 winning-recipe variant",
        "expression": R6_03_60,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R18_02",
        "category": "upper-shadow-up-sub",
        "idea": "R6_03 with SUB-neut + t=0.05.",
        "original": "R6_03 sub variant",
        "expression": R6_03_60,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R18_03",
        "category": "upper-shadow-up-100d",
        "idea": "R6_03 with 100d window for stability.",
        "original": "R6_03 100d variant",
        "expression": R6_03_100,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R18_04",
        "category": "lower-shadow-down",
        "idea": (
            "Mirror of R6_03: lower shadow ((close-low)/close) "
            "averaged on down days only. Long names with long "
            "lower-shadows on down days (rejection of lows, "
            "mean-reversion premium)."
        ),
        "original": "-Mean((C-L)/C * (C<O), 60)",
        "expression": LOWER_SHADOW_DOWN,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R18_05",
        "category": "asym-vol-return-tuned",
        "idea": (
            "R4_02 asym-vol-on-returns (SH=0.94 default) retuned "
            "with INDUSTRY d=4 t=0.05 -- same recipe."
        ),
        "original": "R4_02 winning-recipe variant",
        "expression": R4_02,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
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
