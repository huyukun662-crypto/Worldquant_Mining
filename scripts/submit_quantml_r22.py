"""QuantML round 22: 3 more strictly novel orthogonal shapes.

  R22_01  cross-sectional rank stability: std of rank(returns) over 60d
            (cross-sectional operator + time-series std)
  R22_02  volume-weighted return mean: weighted mean of returns by volume
            (volume-weighting scheme not yet tried)
  R22_03  z-score velocity: ts_delta(ts_zscore(close, 60), 5)
            (derivative of standardised level)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R22_01",
        "category": "rank-stability",
        "idea": (
            "60d std of cross-sectional rank(returns). Captures "
            "rank instability over time -- noisy-rank names. Sign "
            "negative: short rank-noisy (uninvestible, no edge)."
        ),
        "original": "-Std(Rank(Ret), 60)",
        "expression": "-1 * ts_std_dev(rank(returns), 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R22_02",
        "category": "vol-weighted-return-mean",
        "idea": (
            "Volume-weighted mean return over 60d. "
            "ts_mean(returns*volume, 60) / ts_mean(volume, 60). "
            "Different from R8_03 (session mean decomp) -- uses "
            "volume weights to emphasise high-flow days."
        ),
        "original": "Mean(R*V,60) / Mean(V,60)",
        "expression": (
            "ts_mean(returns * volume, 60) / ts_mean(volume, 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R22_03",
        "category": "zscore-velocity",
        "idea": (
            "5-day change in 60-day z-score of close. Derivative of "
            "standardised level -- captures the rate at which a name "
            "is moving through its own distribution. Sign negative: "
            "short fast-moving-up (mean reversion at the z-score "
            "scale)."
        ),
        "original": "-Delta(Zscore(Close,60), 5)",
        "expression": (
            "-1 * ts_delta(ts_zscore(close, 60), 5)"
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
