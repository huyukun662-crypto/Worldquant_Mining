"""QuantML PZ13: cold operators on PV fields. Avoid everything used:
  - ts_corr (heavily used in PZ2-11)
  - mdl77_* (used in D-rounds, F, NCO, NEW)
  - snt_value/snt_buzz/news_indx_perf (PZ12 mostly failed)
  - intraday close-open (D-rounds)
  - winsorize, signed_power, group_zscore (used)
  - ts_skewness/ts_min/ts_max (operator unavailable per prior tests)

  PZ13_01  -ts_kurtosis(returns, 250)              fat tail reversal
  PZ13_02  -ts_partial_corr(vwap, low, high, 500)  partial corr
  PZ13_03  ts_regression(vwap, ts_step(0), 100, lag=0, rettype="SLOPE")
  PZ13_04  -last_diff_value(vwap, 5)               last diff from delayed
  PZ13_05  -ts_decay_exp_window(returns, 60, factor=0.5)  exp-decay returns
  PZ13_06  -ts_count_nans(volume, 250)             data sparsity
  PZ13_07  -hump_decay(returns, 0.05)              hump-decay on returns
  PZ13_08  -ts_av_diff(returns, 60)                avg-diff returns
  PZ13_09  -ts_co_kurtosis(high, low, 250)         co-kurtosis HL
  PZ13_10  -ts_ir(returns, 100)                    information ratio
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
SET_D2 = {
    "universe": "TOP3000", "decay": 2,
    "neutralization": "INDUSTRY", "truncation": 0.03,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ13_01",
        "category": "returns-kurtosis",
        "idea": "-ts_kurtosis(returns, 250) -- fat-tail reversal.",
        "original": "-ts_kurtosis(returns, 250)",
        "expression": "-1 * ts_kurtosis(returns, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ13_02",
        "category": "partial-corr-vwap-low-high",
        "idea": "Partial corr vwap, low controlling for high.",
        "original": "-ts_partial_corr(vwap, low, high, 500)",
        "expression": "-1 * ts_partial_corr(vwap, low, high, 500)",
        "settings_override": SET_D2,
    },
    {
        "id": "QM_PZ13_03",
        "category": "vwap-regression-slope",
        "idea": "vwap regression slope over time.",
        "original": "ts_regression(vwap, ts_step(0), 100, lag=0, rettype='SLOPE')",
        "expression": (
            "ts_regression(vwap, ts_step(0), 100, lag=0, rettype=\"SLOPE\")"
        ),
        "settings_override": SET_D2,
    },
    {
        "id": "QM_PZ13_04",
        "category": "last-diff-vwap",
        "idea": "Last actual diff vwap vs 5-day-prior.",
        "original": "-last_diff_value(vwap, 5)",
        "expression": "-1 * last_diff_value(vwap, 5)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ13_05",
        "category": "returns-exp-decay",
        "idea": "Exponentially-decayed returns over 60d.",
        "original": "-ts_decay_exp_window(returns, 60, factor=0.5)",
        "expression": "-1 * ts_decay_exp_window(returns, 60, factor=0.5)",
        "settings_override": SET_D2,
    },
    {
        "id": "QM_PZ13_06",
        "category": "volume-nans-count",
        "idea": "-ts_count_nans(volume, 250) -- data sparsity proxy.",
        "original": "-ts_count_nans(volume, 250)",
        "expression": "-1 * ts_count_nans(volume, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ13_07",
        "category": "returns-hump-decay",
        "idea": "Hump-decay applied to returns.",
        "original": "-hump_decay(returns, 0.05)",
        "expression": "-1 * hump_decay(returns, 0.05)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ13_08",
        "category": "returns-av-diff",
        "idea": "-ts_av_diff(returns, 60) -- avg actual difference.",
        "original": "-ts_av_diff(returns, 60)",
        "expression": "-1 * ts_av_diff(returns, 60)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ13_09",
        "category": "HL-co-kurtosis",
        "idea": "Co-kurtosis of high and low over 250d.",
        "original": "-ts_co_kurtosis(high, low, 250)",
        "expression": "-1 * ts_co_kurtosis(high, low, 250)",
        "settings_override": SET_D2,
    },
    {
        "id": "QM_PZ13_10",
        "category": "returns-ir",
        "idea": "-ts_ir(returns, 100) -- information ratio of returns.",
        "original": "-ts_ir(returns, 100)",
        "expression": "-1 * ts_ir(returns, 100)",
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
