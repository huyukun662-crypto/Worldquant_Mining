"""QuantML PZ17: explore brand-new operator categories.

  PZ17_01  -bucket(rank(adv20), 5)              quintile bucketing
  PZ17_02  -quantile(returns, driver="gaussian") Gaussian quantile map
  PZ17_03  -s_log_1p(volume)                    symmetric log
  PZ17_04  -arc_tan(returns)                    atan transform
  PZ17_05  -sigmoid(returns)                    sigmoid
  PZ17_06  -tanh(returns)                       tanh
  PZ17_07  -inverse(adv20)                      reciprocal
  PZ17_08  vector_neut(volume, market)          vector neut probe
  PZ17_09  regression_neut(returns, vwap)       regression neut
  PZ17_10  -kth_element(returns, 5)             kth element
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
        "id": "QM_PZ17_01",
        "category": "bucket-adv20-quintile",
        "idea": "Quintile bucket of adv20 rank.",
        "original": "-bucket(rank(adv20), 5)",
        "expression": "-1 * bucket(rank(adv20), 5)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_02",
        "category": "quantile-gaussian",
        "idea": "Quantile-mapped returns with Gaussian driver.",
        "original": '-quantile(returns, driver="gaussian")',
        "expression": "-1 * quantile(returns, driver=\"gaussian\")",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_03",
        "category": "s_log_1p-volume",
        "idea": "Symmetric log of volume.",
        "original": "-s_log_1p(volume)",
        "expression": "-1 * s_log_1p(volume)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_04",
        "category": "arc_tan-returns",
        "idea": "Arctangent of returns.",
        "original": "-arc_tan(returns)",
        "expression": "-1 * arc_tan(returns)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_05",
        "category": "sigmoid-returns",
        "idea": "Sigmoid of returns.",
        "original": "-sigmoid(returns)",
        "expression": "-1 * sigmoid(returns)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_06",
        "category": "tanh-returns",
        "idea": "Tanh of returns.",
        "original": "-tanh(returns)",
        "expression": "-1 * tanh(returns)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_07",
        "category": "inverse-adv20",
        "idea": "Reciprocal of adv20.",
        "original": "-inverse(adv20)",
        "expression": "-1 * inverse(adv20)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_08",
        "category": "vector_neut-volume",
        "idea": "vector_neut probe.",
        "original": "vector_neut(volume, market)",
        "expression": "vector_neut(volume, market)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_09",
        "category": "regression_neut-returns",
        "idea": "regression_neut probe.",
        "original": "regression_neut(returns, vwap)",
        "expression": "regression_neut(returns, vwap)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ17_10",
        "category": "kth_element-returns",
        "idea": "kth_element probe.",
        "original": "-kth_element(returns, 5)",
        "expression": "-1 * kth_element(returns, 5)",
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
