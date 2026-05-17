"""QuantML PZ18: fixed syntax for bucket/kth_element + new cold ops.

  PZ18_01  -bucket(rank(adv20), buckets=5)        proper bucket syntax
  PZ18_02  -kth_element(returns, 1, k=5)          proper kth_element syntax
  PZ18_03  quantile(returns, driver="uniform")    uniform driver
  PZ18_04  -log(adv20)                            direct log
  PZ18_05  -sqrt(adv20)                           sqrt
  PZ18_06  -min(high, vwap) - low                 cross-section min
  PZ18_07  -mod(volume, 1000)                     mod
  PZ18_08  densify(industry)                      densify with Group input
  PZ18_09  nan_out(returns, 100)                  nan_out probe
  PZ18_10  -vec_ir(volume, 100)                   vec_ir probe
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
        "id": "QM_PZ18_01",
        "category": "bucket-adv20-fixed",
        "idea": "-bucket(rank(adv20), buckets=5) proper kwarg.",
        "original": "-bucket(rank(adv20), buckets=5)",
        "expression": "-1 * bucket(rank(adv20), buckets=5)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_02",
        "category": "kth_element-fixed",
        "idea": "kth_element with k= kwarg.",
        "original": "-kth_element(returns, 1, k=5)",
        "expression": "-1 * kth_element(returns, 1, k=5)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_03",
        "category": "quantile-uniform",
        "idea": "quantile with uniform driver.",
        "original": '-quantile(returns, driver="uniform")',
        "expression": "-1 * quantile(returns, driver=\"uniform\")",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_04",
        "category": "log-adv20",
        "idea": "Direct log of adv20.",
        "original": "-log(adv20)",
        "expression": "-1 * log(adv20)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_05",
        "category": "sqrt-adv20",
        "idea": "Sqrt of adv20.",
        "original": "-sqrt(adv20)",
        "expression": "-1 * sqrt(adv20)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_06",
        "category": "min-high-vwap-minus-low",
        "idea": "Cross-section min(high,vwap) - low.",
        "original": "-(min(high, vwap) - low)",
        "expression": "-1 * (min(high, vwap) - low)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_07",
        "category": "mod-volume",
        "idea": "Probe mod operator.",
        "original": "-mod(volume, 1000)",
        "expression": "-1 * mod(volume, 1000)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_08",
        "category": "densify-industry",
        "idea": "densify with proper Group input.",
        "original": "densify(industry)",
        "expression": "densify(industry)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_09",
        "category": "nan_out-returns",
        "idea": "Probe nan_out operator.",
        "original": "nan_out(returns, 100)",
        "expression": "nan_out(returns, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18_10",
        "category": "vec_ir-volume",
        "idea": "Probe vec_ir operator.",
        "original": "-vec_ir(volume, 100)",
        "expression": "-1 * vec_ir(volume, 100)",
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
