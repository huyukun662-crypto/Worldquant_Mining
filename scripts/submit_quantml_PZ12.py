"""QuantML PZ12: 10 cold/niche factors structurally different from PZ1-11.

PZ1-11 mined ts_corr PV (vwap/high/low) heavily. PZ12 explores
underused data fields and operators:
  - alt-data: snt_value, snt_buzz, news_indx_perf (only used as gates before)
  - new operators: signed_power, ts_rank, ts_zscore, ts_delta, group_zscore
  - no mdl77 anywhere

  01 snt_value autocorr 5d
  02 -ts_mean(news_indx_perf, 60)
  03 winsorize(-CoV(snt_buzz, 100), std=3)
  04 ts_corr(snt_value, vwap, 250)
  05 -ts_zscore(vwap, 250)
  06 -ts_rank(vwap, 500)
  07 signed_power(ts_corr(high, low, 500), 1.5)
  08 group_zscore(ts_corr(vwap, delay(vwap, 5), 500), market)
  09 ts_corr(news_indx_perf, returns, 250)
  10 -ts_delta(snt_value, 30)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


SET_IND = {
    "universe": "TOP3000", "decay": 2,
    "neutralization": "INDUSTRY", "truncation": 0.03,
}
SET_SUB = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}
SET_T10 = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.10,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ12_01",
        "category": "snt_value-autocorr",
        "idea": "Sentiment value 5-day autocorr over 250d window.",
        "original": "ts_corr(snt_value, delay(snt_value, 5), 250)",
        "expression": "ts_corr(snt_value, ts_delay(snt_value, 5), 250)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ12_02",
        "category": "news-indx-perf-mean",
        "idea": "Rolling 60-day mean of news index performance, sign-flipped.",
        "original": "-ts_mean(news_indx_perf, 60)",
        "expression": "-1 * ts_mean(news_indx_perf, 60)",
        "settings_override": SET_SUB,
    },
    {
        "id": "QM_PZ12_03",
        "category": "snt-buzz-CoV-winz",
        "idea": "CoV(snt_buzz, 100) winsorized -- sentiment vol regime.",
        "original": "winsorize(-CoV(snt_buzz, 100), std=3)",
        "expression": (
            "winsorize(-1 * ts_std_dev(snt_buzz, 100) / "
            "ts_mean(snt_buzz, 100), std=3)"
        ),
        "settings_override": SET_T10,
    },
    {
        "id": "QM_PZ12_04",
        "category": "snt_value-vwap-corr",
        "idea": "Cross-corr of sentiment value vs vwap over 250d.",
        "original": "ts_corr(snt_value, vwap, 250)",
        "expression": "ts_corr(snt_value, vwap, 250)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ12_05",
        "category": "vwap-zscore-rev",
        "idea": "Negative 250d z-score of vwap (mean reversion).",
        "original": "-ts_zscore(vwap, 250)",
        "expression": "-1 * ts_zscore(vwap, 250)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ12_06",
        "category": "vwap-ts_rank-rev",
        "idea": "Negative time-series rank of vwap over 500d (percentile reversal).",
        "original": "-ts_rank(vwap, 500)",
        "expression": "-1 * ts_rank(vwap, 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ12_07",
        "category": "HL-corr-signed-pow",
        "idea": "signed_power(ts_corr(high, low, 500), 1.5) -- amplify magnitude.",
        "original": "signed_power(ts_corr(high, low, 500), 1.5)",
        "expression": "signed_power(ts_corr(high, low, 500), 1.5)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ12_08",
        "category": "vwap-autocorr-group_zscore",
        "idea": "group_zscore over market of vwap autocorr 5d 500.",
        "original": "group_zscore(ts_corr(vwap, delay(vwap,5), 500), market)",
        "expression": (
            "group_zscore(ts_corr(vwap, ts_delay(vwap, 5), 500), market)"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ12_09",
        "category": "news-returns-corr",
        "idea": "Cross-corr news_indx_perf vs returns over 250d.",
        "original": "ts_corr(news_indx_perf, returns, 250)",
        "expression": "ts_corr(news_indx_perf, returns, 250)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ12_10",
        "category": "snt_value-momentum-rev",
        "idea": "Negative 30-day delta of sentiment value (momentum reversal).",
        "original": "-ts_delta(snt_value, 30)",
        "expression": "-1 * ts_delta(snt_value, 30)",
        "settings_override": SET_IND,
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
