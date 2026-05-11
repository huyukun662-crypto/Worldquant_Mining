"""QuantML round 9: more orthogonal shapes.

Winners so far span two shape families:
  variance asymmetry  (R6_01, OA24)        std-tail shape
  session-mean diff   (R8_03)              mean-of-conditional shape

R9 introduces 5 new RATIO/REGRESSION/CONDITIONAL shapes, each
mathematically distinct from the above and from each other:

  R9_01 overnight Sharpe      mean / std (overnight only)
  R9_02 Sortino-like          mean / downside-std (return universe)
  R9_03 vol regime ratio      short-vol / long-vol
  R9_04 sub-industry beta     peer-relative beta (low-beta anomaly)
  R9_05 conditional reversal  short return * sign(long trend)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R9_01",
        "category": "overnight-sharpe",
        "idea": (
            "Information ratio of overnight gaps over 60d: "
            "mean(overnight) / std(overnight). Distinct from R8_03 "
            "which is a session-mean DIFFERENCE; this is a RATIO "
            "and confined to the overnight channel only."
        ),
        "original": "Mean(Overnight,60) / Std(Overnight,60)",
        "expression": (
            "ts_mean(open / ts_delay(close, 1) - 1, 60) "
            "/ ts_std_dev(open / ts_delay(close, 1) - 1, 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R9_02",
        "category": "sortino-like",
        "idea": (
            "Sortino-like ratio: 60d mean return per unit of "
            "downside std. Different from a Sharpe -- only down-"
            "side vol enters the denominator. Long high-Sortino "
            "names (risk-adjusted return premium)."
        ),
        "original": "Mean(Ret,60) / Std(Ret*(Ret<0),60)",
        "expression": (
            "ts_mean(returns, 60) "
            "/ ts_std_dev(returns * less(returns, 0), 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R9_03",
        "category": "vol-regime-ratio",
        "idea": (
            "20d std of returns divided by 60d std of returns. "
            "Indicates vol regime: > 1 = recently elevated vol "
            "vs longer baseline. Short names in elevated regime "
            "(vol-mean-reversion premium)."
        ),
        "original": "Std(Ret,20) / Std(Ret,60)",
        "expression": (
            "-1 * ts_std_dev(returns, 20) / ts_std_dev(returns, 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R9_04",
        "category": "subindustry-beta",
        "idea": (
            "60-day regression slope of returns on sub-industry "
            "mean returns. Captures within-peer-group beta. Low-"
            "beta anomaly: short high-beta-within-peer names."
        ),
        "original": "Slope(Ret, GroupMean(Ret, SubIndustry), 60)",
        "expression": (
            "-1 * ts_regression(returns, "
            "group_mean(returns, 1, subindustry), 60, rettype=2)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R9_05",
        "category": "conditional-reversal",
        "idea": (
            "Short-window mean return multiplied by the sign of "
            "the long-window mean return. Reversal of recent moves "
            "conditional on the slow trend direction; sign captures "
            "an interaction not present in pure short reversal."
        ),
        "original": "-Mean(Ret,5) * Sign(Mean(Ret,252))",
        "expression": (
            "-1 * ts_mean(returns, 5) "
            "* sign(ts_mean(returns, 252))"
        ),
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
