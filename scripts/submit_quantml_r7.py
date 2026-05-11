"""QuantML round 7 (redesigned): 5 structurally ORTHOGONAL factors.

The earlier R7 design re-used the asym-variance shape across 5
channels -- structurally identical, high cross-correlation. This
redesign uses 5 different OPERATOR FAMILIES, each capturing a
qualitatively different effect:

  R7_01  auto-correlation       linear association of consecutive returns
  R7_02  coefficient of var.    ratio of moments (std/mean)
  R7_03  sign-streak persistence sign-indicator mean (count-based)
  R7_04  long-term rank reversal ordinal time-rank
  R7_05  volume shock           ts_rank(volume) short vs long

Each one should be uncorrelated with R6_01/OA24 (variance-asymmetry
of price) and with each other.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R7_01",
        "category": "auto-correlation",
        "idea": (
            "60-day auto-correlation of daily returns. Positive = "
            "momentum-like persistence; negative = reversal. Sign: "
            "short positive (momentum already priced) -- low-vol "
            "anomaly cousin via return persistence."
        ),
        "original": "Corr(Ret, Delay(Ret,1), 60)",
        "expression": "-1 * ts_corr(returns, ts_delay(returns, 1), 60)",
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R7_02",
        "category": "coef-of-variation",
        "idea": (
            "60-day coefficient of variation = std(close)/mean(close). "
            "Relative dispersion ignoring level. High CV = unstable "
            "names. Sign: negative (low-vol anomaly)."
        ),
        "original": "Std(Close,60) / Mean(Close,60)",
        "expression": "-1 * ts_std_dev(close, 60) / ts_mean(close, 60)",
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R7_03",
        "category": "sign-streak",
        "idea": (
            "60-day mean of sign(returns). Counts the net direction "
            "balance. Persistent up-day count = trend-followers' "
            "playground; short it (mean-reversion at this horizon)."
        ),
        "original": "Mean(Sign(Ret), 60)",
        "expression": "-1 * ts_mean(sign(returns), 60)",
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R7_04",
        "category": "rank-reversal",
        "idea": (
            "Cross-sectional position within a 252-day window via "
            "ts_rank(close, 252). Long names at the BOTTOM of their "
            "annual range (rank low) -- annual mean-reversion."
        ),
        "original": "-1 * TsRank(Close, 252)",
        "expression": "-1 * ts_rank(close, 252)",
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R7_05",
        "category": "volume-shock",
        "idea": (
            "Short-window minus long-window time-rank of volume: "
            "ts_rank(volume, 5) - ts_rank(volume, 60). Spikes "
            "above the slow baseline. Long the spike (information "
            "flow precedes price)."
        ),
        "original": "TsRank(Vol, 5) - TsRank(Vol, 60)",
        "expression": "ts_rank(volume, 5) - ts_rank(volume, 60)",
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
