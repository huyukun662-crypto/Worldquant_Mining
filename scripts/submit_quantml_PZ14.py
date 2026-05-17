"""QuantML PZ14: extend PZ13 winner (ts_count_nans) + probe ts_regression
rettype + winsorize-wrap ts_av_diff.

PZ13 finding: ts_count_nans, last_diff_value, ts_av_diff, ts_regression
are AVAILABLE.  ts_count_nans(volume, 250) clean SH 1.27.

  PZ14_01  -ts_count_nans(returns, 250)
  PZ14_02  -ts_count_nans(volume, 500)
  PZ14_03  -ts_count_nans(high - low, 250)
  PZ14_04  -ts_count_nans(adv20, 250)
  PZ14_05  -ts_count_nans(vwap, 250)
  PZ14_06  ts_regression(vwap, ts_step(0), 100, lag=0, rettype=2)  predicted value
  PZ14_07  ts_regression(vwap, ts_step(0), 100, lag=0, rettype=4)  another rettype
  PZ14_08  winsorize(-ts_av_diff(returns, 60), std=3)              tame the TO
  PZ14_09  -last_diff_value(returns, 5)
  PZ14_10  -ts_decay_linear(ts_av_diff(returns, 60), 14)           smooth TO
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.05,
}
SET_T10 = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.10,
}
SET_D2 = {
    "universe": "TOP3000", "decay": 2,
    "neutralization": "INDUSTRY", "truncation": 0.03,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ14_01",
        "category": "count_nans-returns",
        "idea": "-ts_count_nans(returns, 250)",
        "original": "-ts_count_nans(returns, 250)",
        "expression": "-1 * ts_count_nans(returns, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ14_02",
        "category": "count_nans-volume-500",
        "idea": "-ts_count_nans(volume, 500) -- longer window of PZ13 winner.",
        "original": "-ts_count_nans(volume, 500)",
        "expression": "-1 * ts_count_nans(volume, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ14_03",
        "category": "count_nans-HLrange",
        "idea": "-ts_count_nans(high - low, 250)",
        "original": "-ts_count_nans(high-low, 250)",
        "expression": "-1 * ts_count_nans(high - low, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ14_04",
        "category": "count_nans-adv20",
        "idea": "-ts_count_nans(adv20, 250)",
        "original": "-ts_count_nans(adv20, 250)",
        "expression": "-1 * ts_count_nans(adv20, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ14_05",
        "category": "count_nans-vwap",
        "idea": "-ts_count_nans(vwap, 250)",
        "original": "-ts_count_nans(vwap, 250)",
        "expression": "-1 * ts_count_nans(vwap, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ14_06",
        "category": "regression-rettype-2",
        "idea": "ts_regression(vwap, step, 100, lag=0, rettype=2).",
        "original": "ts_regression(vwap, ts_step(0), 100, lag=0, rettype=2)",
        "expression": (
            "ts_regression(vwap, ts_step(0), 100, lag=0, rettype=2)"
        ),
        "settings_override": SET_D2,
    },
    {
        "id": "QM_PZ14_07",
        "category": "regression-rettype-4",
        "idea": "ts_regression(vwap, step, 100, lag=0, rettype=4).",
        "original": "ts_regression(vwap, ts_step(0), 100, lag=0, rettype=4)",
        "expression": (
            "ts_regression(vwap, ts_step(0), 100, lag=0, rettype=4)"
        ),
        "settings_override": SET_D2,
    },
    {
        "id": "QM_PZ14_08",
        "category": "av_diff-returns-winz",
        "idea": "winsorize(-ts_av_diff(returns, 60), std=3) to tame TO.",
        "original": "winsorize(-ts_av_diff(returns, 60), std=3)",
        "expression": "winsorize(-1 * ts_av_diff(returns, 60), std=3)",
        "settings_override": SET_T10,
    },
    {
        "id": "QM_PZ14_09",
        "category": "last_diff-returns",
        "idea": "-last_diff_value(returns, 5).",
        "original": "-last_diff_value(returns, 5)",
        "expression": "-1 * last_diff_value(returns, 5)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ14_10",
        "category": "av_diff-returns-decay",
        "idea": "ts_decay_linear smoothing of av_diff.",
        "original": "-ts_decay_linear(ts_av_diff(returns, 60), 14)",
        "expression": (
            "-1 * ts_decay_linear(ts_av_diff(returns, 60), 14)"
        ),
        "settings_override": SET,
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
