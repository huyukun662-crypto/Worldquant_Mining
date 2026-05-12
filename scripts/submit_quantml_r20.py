"""QuantML round 20: 3 strictly novel orthogonal shapes.

Existing 4 viables cluster as:
  A. OHLC channel statistics (R6_01 body asym-var, OA24 high/low asym-var,
                              R16_05 body signed-squared mean)
  B. Session-mean decomposition (R8_03)

This round delivers 3 shapes that DON'T fit either:

  R20_01  Garman-Klass-style squared-moment difference
           (range^2 vs returns^2) -- no asymmetric mask
  R20_02  Volume-weighted shadow asymmetry
           normalised by dollar volume -- product of geometry and flow
  R20_03  Close vs daily mid-point (high+low)/2 persistence
           -- never tried; anchor is mid, not open or prev-close
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R20_01",
        "category": "gk-range-vs-return-vol",
        "idea": (
            "Garman-Klass-like estimator: 60d mean of (high-low)/close "
            "squared, MINUS 60d mean of returns squared. Captures "
            "intraday range vol IN EXCESS of close-to-close return "
            "vol. High excess = high intraday churn but little net "
            "movement -- short these (volatility insurance over-paid)."
        ),
        "original": "-(Mean((H-L)^2/C^2,60) - Mean(R^2,60))",
        "expression": (
            "-1 * (ts_mean(power((high - low) / close, 2), 60) "
            "- ts_mean(power(returns, 2), 60))"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R20_02",
        "category": "vol-weighted-shadow-asym",
        "idea": (
            "Volume-weighted shadow asymmetry: 60d mean of "
            "(high-close)*volume minus (close-low)*volume, all "
            "normalised by 60d mean of close*volume to make "
            "unitless. Captures aggressive selling-into-highs vs "
            "buying-from-lows. Sign negative (selling-dominant -> "
            "short)."
        ),
        "original": "-(Mean((H-C)*V,60) - Mean((C-L)*V,60))/Mean(C*V,60)",
        "expression": (
            "-1 * (ts_mean((high - close) * volume, 60) "
            "- ts_mean((close - low) * volume, 60)) "
            "/ ts_mean(close * volume, 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R20_03",
        "category": "midpoint-deviation",
        "idea": (
            "60d mean of (close - (high+low)/2) / close. Daily "
            "deviation of close from the day's mid-point. Persistent "
            "positive = closes near high (buying pressure dominates "
            "intraday). Long it. Different from session decomp "
            "(uses mid not open/prev-close)."
        ),
        "original": "Mean((C-(H+L)/2)/C, 60)",
        "expression": (
            "ts_mean((close - (high + low) / 2) / close, 60)"
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
