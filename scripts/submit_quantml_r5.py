"""QuantML round 5: push past SH=1.25.

R4_02 broke through to FIT=1.04 (the first factor in this study with
FIT > 1). It uses the down-vol-minus-up-vol shape on returns with
explicit `less(returns,0)` / `greater(returns,0)` masks rather than
`min(returns,0)` / `max(returns,0)`, and got 0.94 SH (vs 0.68 from
R3_02 which used the min/max formulation -- same algebra, different
numerical handling on NaNs).

Round 5: target SH > 1.25. Five new factors:

  R5_01  R4_02 tuned -- tighter truncation + SUBINDUSTRY
  R5_02  z-sum(R4_02, R2_05) -- best two uncorrelated singletons
  R5_03  rolling market beta -- distinct from R2's idio-vol
  R5_04  close-vs-vwap divergence -- intraday position
  R5_05  range-weighted volume -- money-at-risk indicator
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

R4_02_EXPR = (
    "ts_std_dev(returns * less(returns, 0), 100) "
    "- ts_std_dev(returns * greater(returns, 0), 100)"
)
R2_05_EXPR = (
    "-1 * ts_mean(power(ts_zscore(returns, 60), 3), 60)"
)

FACTORS: list[dict] = [
    {
        "id": "QM_R5_01",
        "category": "downup-vol-tuned",
        "idea": (
            "Round-4 R4_02 tuned: tighter 0.05 truncation + "
            "SUBINDUSTRY neutralization. The signal is sub-industry "
            "level (downside-vol premium varies by industry stress), "
            "so SUBINDUSTRY should capture residual after INDUSTRY."
        ),
        "original": "Round-4 R4_02 with tighter settings",
        "expression": R4_02_EXPR,
        "settings_override": {
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R5_02",
        "category": "z-sum-downvol-skew",
        "idea": (
            "Z-sum of R4_02 (downside-vol premium, SH=0.94) and "
            "R2_05 (negative skew, SH=0.84). The two are structurally "
            "orthogonal: one is variance-tail, the other is third-"
            "moment shape. Their cross-sectional z-scores should add."
        ),
        "original": "Z(R4_02) + Z(R2_05)",
        "expression": (
            f"ts_zscore({R4_02_EXPR}, 20) "
            f"+ ts_zscore({R2_05_EXPR}, 20)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R5_03",
        "category": "rolling-market-beta",
        "idea": (
            "60-day rolling regression slope of returns on market "
            "mean returns. High-beta names underperform after "
            "industry-neut (low-beta anomaly); short high-beta. "
            "Distinct from R2_01 (idio-vol = residual std) which "
            "discards beta direction."
        ),
        "original": "Slope(Ret, MktRet, 60)",
        "expression": (
            "-1 * ts_regression(returns, "
            "group_mean(returns, 1, market), 60, rettype=2)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R5_04",
        "category": "close-vwap-divergence",
        "idea": (
            "ts_mean((close - vwap) / vwap, 20). Persistent positive "
            "close-vs-vwap = afternoon buying pressure -> long. "
            "Captures intraday positional info that returns alone "
            "miss."
        ),
        "original": "Mean((Close - Vwap) / Vwap, 20)",
        "expression": "ts_mean((close - vwap) / vwap, 20)",
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R5_05",
        "category": "range-x-volume",
        "idea": (
            "Mean of (high-low)*volume over 20d = money-at-risk "
            "per day. High M-a-R = institutional flow concentration. "
            "Sign: negative (M-a-R captures over-traded / over-"
            "owned, those underperform on average)."
        ),
        "original": "Mean((H-L) * Volume, 20)",
        "expression": "-1 * ts_mean((high - low) * volume, 20)",
        "settings_override": {
            "decay": 4,
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
