"""QuantML round 19: 5 fresh shapes with winning recipe.

R18 confirmed empirical wall at SH=0.94 for R6_03 / R4_02. Try
5 new structures with the winning recipe (INDUSTRY d=4 t=0.05):

  R19_01  intraday-body autocorrelation
  R19_02  VWAP-deviation non-directional vol
  R19_03  R4_02 with signed_power(returns, 2) transform
  R19_04  range-body coupling time corr
  R19_05  volume-vs-signed-magnitude asym
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R19_01",
        "category": "body-autocorr",
        "idea": (
            "60d corr of intraday body with its 1-day lag. "
            "Body-persistent names = intraday momentum/trend "
            "regime; short (mean reversion at the body level)."
        ),
        "original": "-Corr(Body, Delay(Body,1), 60)",
        "expression": (
            "-1 * ts_corr((close - open) / open, "
            "ts_delay((close - open) / open, 1), 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R19_02",
        "category": "vwap-dev-vol",
        "idea": (
            "100d std of |close - vwap| / vwap. Non-directional "
            "intraday dispersion. Short high-dispersion names."
        ),
        "original": "-Std(|C-VWAP|/VWAP, 100)",
        "expression": (
            "-1 * ts_std_dev(abs(close - vwap) / vwap, 100)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R19_03",
        "category": "asym-sigpow2-return",
        "idea": (
            "R4_02 with signed_power(returns, 2) replacing returns. "
            "The signed-squared transform that lifted R10_04 -> "
            "R16_05; apply to the conditional-downvol shape."
        ),
        "original": "R4_02 signed_power(R,2) variant",
        "expression": (
            "ts_std_dev(signed_power(returns, 2) * less(returns, 0), 100) "
            "- ts_std_dev(signed_power(returns, 2) "
            "* greater(returns, 0), 100)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R19_04",
        "category": "range-body-corr",
        "idea": (
            "60d corr between daily range (h-l)/close and abs body "
            "|c-o|/close. Strong corr = decisive moves dominate; "
            "weak corr = range from indecision. Sign: negative "
            "(strong-trend names underperform)."
        ),
        "original": "-Corr((H-L)/C, |C-O|/C, 60)",
        "expression": (
            "-1 * ts_corr((high - low) / close, "
            "abs(close - open) / close, 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R19_05",
        "category": "vol-signed-mag-asym",
        "idea": (
            "60d corr(volume, returns) MINUS corr(volume, "
            "abs(returns)). Positive = volume tracks direction "
            "more than magnitude (directional flow). Long it."
        ),
        "original": "Corr(V, R, 60) - Corr(V, |R|, 60)",
        "expression": (
            "ts_corr(volume, returns, 60) "
            "- ts_corr(volume, abs(returns), 60)"
        ),
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
