"""QuantML round 21: 3 fresh orthogonal shapes.

R20 produced 0 viables (R20_01 errored on unit, R20_02/R20_03 weak).
R21:

  R21_01  GK-style: std((H-L)/C, 60) - std(close-to-close ret, 60)
           Uses ts_std_dev (avoid `power` unit issue)
  R21_02  VWAP momentum: fast vwap mean / slow vwap mean
  R21_03  Kaufman efficiency ratio: directional move / path length
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R21_01",
        "category": "gk-range-vs-return-vol-v2",
        "idea": (
            "60d std of (high-low)/close minus 60d std of "
            "(close/delay(close,1)-1). Captures intraday range vol "
            "in excess of close-to-close return vol. Short high-"
            "excess (range without trend = vol insurance over-paid)."
        ),
        "original": "Std((H-L)/C,60) - Std(C/Delay(C,1)-1,60)",
        "expression": (
            "-1 * (ts_std_dev((high - low) / close, 60) "
            "- ts_std_dev(close / ts_delay(close, 1) - 1, 60))"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R21_02",
        "category": "vwap-momentum",
        "idea": (
            "5d mean VWAP relative to 60d mean VWAP. Fast-vs-slow "
            "in the VWAP channel (institutional execution path) "
            "rather than close. Sign negative -- fast > slow means "
            "recent acceleration is priced in; short."
        ),
        "original": "-(Mean(VWAP,5)/Mean(VWAP,60) - 1)",
        "expression": (
            "-1 * (ts_mean(vwap, 5) / ts_mean(vwap, 60) - 1)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R21_03",
        "category": "kaufman-efficiency",
        "idea": (
            "Kaufman efficiency ratio over 60d: |close - delay(close, "
            "60)| / sum(|close - delay(close, 1)|, 60). Directional "
            "displacement divided by total path. High = clean trend, "
            "Low = choppy mean-reversion. Sign negative: short "
            "clean-trenders (momentum already priced)."
        ),
        "original": "-|C - Delay(C,60)| / Sum(|C - Delay(C,1)|, 60)",
        "expression": (
            "-1 * abs(close - ts_delay(close, 60)) "
            "/ ts_sum(abs(close - ts_delay(close, 1)), 60)"
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
