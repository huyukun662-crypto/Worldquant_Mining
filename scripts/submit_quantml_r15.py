"""QuantML round 15: push two near-viables across SH=1.3.

Two factors are FIT > 1 but SH < 1.3 -- worth setting-space tuning:

  R14_03 beta-time-variation  SH=0.94 FIT=1.43 RET=0.29  TOP3000 d=4 IND t=0.08
  R10_04 intraday-body-skew    SH=1.07 FIT=1.10 RET=0.13  TOP3000 d=4 MAR t=0.08
  (R14_01 already failed SUBINDUSTRY d=16 t=0.04 on R10_04)

R15 tests 5 setting tuples for these two:

  R15_01  R14_03 beta-vol     d=8  INDUSTRY  t=0.05
  R15_02  R14_03 beta-vol     d=8  SUBINDUSTRY t=0.05
  R15_03  R10_04 body-skew    d=4  INDUSTRY  t=0.05  (was MARKET)
  R15_04  R10_04 body-skew    d=8  MARKET    t=0.05
  R15_05  R10_04 body-skew    d=4  SUBINDUSTRY t=0.05
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


BETA_TV = (
    "-1 * ts_std_dev(ts_regression(returns, "
    "group_mean(returns, 1, market), 60, rettype=2), 60)"
)
BODY_SKEW = (
    "-1 * ts_mean(power(ts_zscore("
    "(close - open) / open, 60), 3), 60)"
)


FACTORS: list[dict] = [
    {
        "id": "QM_R15_01",
        "category": "beta-tv-ind-d8-t05",
        "idea": (
            "R14_03 with decay=8 + tighter truncation 0.05 to "
            "compress P&L noise; INDUSTRY-neut kept."
        ),
        "original": "R14_03 setting variant",
        "expression": BETA_TV,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R15_02",
        "category": "beta-tv-sub-d8-t05",
        "idea": (
            "R14_03 with SUBINDUSTRY-neut + decay=8 + trunc=0.05. "
            "Beta instability may be sub-industry phenomenon."
        ),
        "original": "R14_03 setting variant",
        "expression": BETA_TV,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R15_03",
        "category": "body-skew-ind-d4-t05",
        "idea": (
            "R10_04 with INDUSTRY-neut (was MARKET) + tighter "
            "trunc 0.05. Industry effect was suppressed by MARKET-"
            "neut; try keeping it."
        ),
        "original": "R10_04 setting variant",
        "expression": BODY_SKEW,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R15_04",
        "category": "body-skew-mkt-d8-t05",
        "idea": (
            "R10_04 with MARKET-neut kept + decay=8 + trunc=0.05. "
            "Mild TO compression to lift SH."
        ),
        "original": "R10_04 setting variant",
        "expression": BODY_SKEW,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
            "neutralization": "MARKET",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R15_05",
        "category": "body-skew-sub-d4-t05",
        "idea": (
            "R10_04 with SUBINDUSTRY-neut + trunc=0.05. Tightest "
            "neutralization stripping plus tight bets."
        ),
        "original": "R10_04 setting variant",
        "expression": BODY_SKEW,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
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
