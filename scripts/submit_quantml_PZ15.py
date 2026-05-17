"""QuantML PZ15: extend ts_count_nans winner + new cold operators.

Finding: ts_count_nans(volume, 500) cleared SELF_CORRELATION; W=250
variants all clustered at ~0.80 self-corr. Try even longer windows
and combinations. Also probe more cold operators.

  PZ15_01  -ts_count_nans(volume, 750)
  PZ15_02  -ts_count_nans(volume, 1000)
  PZ15_03  -ts_count_nans(returns, 500)
  PZ15_04  -ts_count_nans(high, 500)
  PZ15_05  -ts_count_nans(low, 500)
  PZ15_06  ts_av_diff(returns, 250)                        longer av_diff window
  PZ15_07  -densify(returns) - cross-section densify        cold op probe
  PZ15_08  -pasteurize(vwap)                                cold op probe
  PZ15_09  -ts_zero_to_nan(volume)                          cold op probe
  PZ15_10  -ts_count_nans(volume, 500) + -ts_count_nans(adv20, 500)  composite
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


FACTORS: list[dict] = [
    {
        "id": "QM_PZ15_01",
        "category": "count_nans-volume-750",
        "idea": "-ts_count_nans(volume, 750)",
        "original": "-ts_count_nans(volume, 750)",
        "expression": "-1 * ts_count_nans(volume, 750)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_02",
        "category": "count_nans-volume-1000",
        "idea": "-ts_count_nans(volume, 1000)",
        "original": "-ts_count_nans(volume, 1000)",
        "expression": "-1 * ts_count_nans(volume, 1000)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_03",
        "category": "count_nans-returns-500",
        "idea": "-ts_count_nans(returns, 500)",
        "original": "-ts_count_nans(returns, 500)",
        "expression": "-1 * ts_count_nans(returns, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_04",
        "category": "count_nans-high-500",
        "idea": "-ts_count_nans(high, 500)",
        "original": "-ts_count_nans(high, 500)",
        "expression": "-1 * ts_count_nans(high, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_05",
        "category": "count_nans-low-500",
        "idea": "-ts_count_nans(low, 500)",
        "original": "-ts_count_nans(low, 500)",
        "expression": "-1 * ts_count_nans(low, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_06",
        "category": "av_diff-returns-250",
        "idea": "-ts_av_diff(returns, 250) longer window to tame TO.",
        "original": "-ts_av_diff(returns, 250)",
        "expression": "-1 * ts_av_diff(returns, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_07",
        "category": "densify-returns",
        "idea": "Probe densify operator on returns.",
        "original": "-densify(returns)",
        "expression": "-1 * densify(returns)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_08",
        "category": "pasteurize-vwap",
        "idea": "Probe pasteurize operator on vwap.",
        "original": "-pasteurize(vwap)",
        "expression": "-1 * pasteurize(vwap)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_09",
        "category": "ts_zero_to_nan-volume",
        "idea": "Probe ts_zero_to_nan operator.",
        "original": "-ts_zero_to_nan(volume)",
        "expression": "-1 * ts_zero_to_nan(volume)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ15_10",
        "category": "count_nans-volume-plus-adv20",
        "idea": "Sum of count_nans on volume and adv20.",
        "original": "-ts_count_nans(volume,500) -ts_count_nans(adv20,500)",
        "expression": (
            "-1 * ts_count_nans(volume, 500) + "
            "-1 * ts_count_nans(adv20, 500)"
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
