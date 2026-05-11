"""QuantML round 17: push R14_03 beta-time-variation across SH=1.3.

R14_03 (-std of rolling 60d beta, 60d outer) has FIT=1.43, RET=29%,
but SH=0.94 -- high vol drags SH down. R15 tested IND/SUB at d=8
t=0.05; both <1.0. Try 5 untested settings:

  R17_01  MARKET-neut          beta is market-related
  R17_02  d=16 INDUSTRY        heavy smoothing
  R17_03  t=0.10 INDUSTRY      looser truncation -> more
                                diversification -> lower vol
  R17_04  120d inner beta      smoother beta estimate
  R17_05  120d inner + outer   maximum smoothing
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


def beta_vol(inner: int, outer: int) -> str:
    return (
        f"-1 * ts_std_dev(ts_regression(returns, "
        f"group_mean(returns, 1, market), {inner}, rettype=2), {outer})"
    )


FACTORS: list[dict] = [
    {
        "id": "QM_R17_01",
        "category": "beta-tv-mkt",
        "idea": (
            "R14_03 with MARKET-neut. Beta is a market-relative "
            "quantity; MARKET-neut should be the natural home."
        ),
        "original": "R14_03 MARKET-neut variant",
        "expression": beta_vol(60, 60),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "MARKET",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R17_02",
        "category": "beta-tv-d16",
        "idea": (
            "R14_03 with decay=16 for heavy TO smoothing -- "
            "compress P&L noise to lift SH."
        ),
        "original": "R14_03 d=16 variant",
        "expression": beta_vol(60, 60),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 16,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R17_03",
        "category": "beta-tv-t10",
        "idea": (
            "R14_03 with looser 0.10 truncation -- more "
            "diversification -> lower P&L vol -> higher SH."
        ),
        "original": "R14_03 looser-trunc variant",
        "expression": beta_vol(60, 60),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.10,
        },
    },
    {
        "id": "QM_R17_04",
        "category": "beta-tv-inner120",
        "idea": (
            "R14_03 with 120d inner regression window (smoother "
            "beta estimate) and 60d outer std."
        ),
        "original": "R14_03 inner120 variant",
        "expression": beta_vol(120, 60),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R17_05",
        "category": "beta-tv-inner-outer-120",
        "idea": (
            "R14_03 with 120d/120d for max smoothing. Captures "
            "slow regime shifts in beta."
        ),
        "original": "R14_03 inner120 + outer120 variant",
        "expression": beta_vol(120, 120),
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
