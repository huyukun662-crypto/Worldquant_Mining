"""QuantML PZ16: more cold operators + ts_count_nans field variants.

  PZ16_01  -ts_count_nans(cap, 500)                       cap field
  PZ16_02  -ts_count_nans(vwap, 500)                      vwap (untested W=500)
  PZ16_03  -ts_count_nans(volume, 500) - ts_count_nans(returns, 500)  composite diff
  PZ16_04  -ts_count_nans(volume, 500) * ts_count_nans(returns, 500)  composite product
  PZ16_05  log(1 + ts_count_nans(volume, 500))            log transform
  PZ16_06  signed_power(-ts_count_nans(volume, 500), 0.5)  sqrt transform
  PZ16_07  vec_count(volume)                              vec op probe
  PZ16_08  is_nan(volume)                                 is_nan op probe
  PZ16_09  nan_mask(returns, 1)                           nan_mask op probe
  PZ16_10  replace(returns, nan, 0)                       replace op probe
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
        "id": "QM_PZ16_01",
        "category": "count_nans-cap-500",
        "idea": "-ts_count_nans(cap, 500) -- market cap sparsity.",
        "original": "-ts_count_nans(cap, 500)",
        "expression": "-1 * ts_count_nans(cap, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_02",
        "category": "count_nans-vwap-500",
        "idea": "-ts_count_nans(vwap, 500).",
        "original": "-ts_count_nans(vwap, 500)",
        "expression": "-1 * ts_count_nans(vwap, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_03",
        "category": "count_nans-vol-minus-returns",
        "idea": "Composite diff of count_nans.",
        "original": "-ts_count_nans(volume,500) - ts_count_nans(returns,500)",
        "expression": (
            "-1 * ts_count_nans(volume, 500) - "
            "ts_count_nans(returns, 500)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_04",
        "category": "count_nans-vol-times-returns",
        "idea": "Product of count_nans (volume * returns).",
        "original": "-ts_count_nans(volume,500) * ts_count_nans(returns,500)",
        "expression": (
            "-1 * ts_count_nans(volume, 500) * "
            "ts_count_nans(returns, 500)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_05",
        "category": "count_nans-vol-log",
        "idea": "log transform of count_nans (volume).",
        "original": "-log(1 + ts_count_nans(volume,500))",
        "expression": "-1 * log(1 + ts_count_nans(volume, 500))",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_06",
        "category": "count_nans-vol-sqrt",
        "idea": "signed_power(-count_nans, 0.5).",
        "original": "signed_power(-ts_count_nans(volume,500), 0.5)",
        "expression": (
            "signed_power(-1 * ts_count_nans(volume, 500), 0.5)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_07",
        "category": "vec_count-volume",
        "idea": "Probe vec_count operator on volume.",
        "original": "vec_count(volume)",
        "expression": "vec_count(volume)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_08",
        "category": "is_nan-volume",
        "idea": "Probe is_nan operator on volume.",
        "original": "-is_nan(volume)",
        "expression": "-1 * is_nan(volume)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_09",
        "category": "nan_mask-returns",
        "idea": "Probe nan_mask operator on returns.",
        "original": "-nan_mask(returns, 1)",
        "expression": "-1 * nan_mask(returns, 1)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ16_10",
        "category": "replace-returns-nan",
        "idea": "Probe replace operator on returns.",
        "original": "-replace(returns, nan, 0)",
        "expression": "-1 * replace(returns, nan, 0)",
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
