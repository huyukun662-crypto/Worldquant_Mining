"""QuantML PZ18Q: fix -1 * quantile(returns, driver="gaussian")
which failed: TO 83.95% > 70%, FIT 0.77 < 1.

Root cause: returns is daily, so quantile changes daily -> huge TO.
Fixes:
  1. Smooth output with ts_decay_linear / ts_mean
  2. Smooth input (use ts_mean(returns, W) before quantile)
  3. winsorize to clip outlier weights
  4. Use longer ts decay & higher truncation

  PZ18Q_01  -ts_mean(quantile(returns, driver="gaussian"), 60)
  PZ18Q_02  -ts_decay_linear(quantile(returns, driver="gaussian"), 30)
  PZ18Q_03  -quantile(ts_mean(returns, 60), driver="gaussian")
  PZ18Q_04  -quantile(ts_mean(returns, 250), driver="gaussian")
  PZ18Q_05  winsorize(-quantile(returns, driver="gaussian"), std=2) + decay
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


SET = {
    "universe": "TOP3000", "decay": 10,
    "neutralization": "INDUSTRY", "truncation": 0.08,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ18Q_01",
        "category": "quantile-output-mean60",
        "idea": "Smooth quantile output over 60 days.",
        "original": '-ts_mean(quantile(returns, driver="gaussian"), 60)',
        "expression": (
            "-1 * ts_mean(quantile(returns, driver=\"gaussian\"), 60)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18Q_02",
        "category": "quantile-output-decay30",
        "idea": "ts_decay_linear smoothing 30d on quantile output.",
        "original": '-ts_decay_linear(quantile(returns, driver="gaussian"), 30)',
        "expression": (
            "-1 * ts_decay_linear("
            "quantile(returns, driver=\"gaussian\"), 30)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18Q_03",
        "category": "quantile-input-mean60",
        "idea": "Smooth INPUT first then quantile.",
        "original": '-quantile(ts_mean(returns, 60), driver="gaussian")',
        "expression": (
            "-1 * quantile(ts_mean(returns, 60), driver=\"gaussian\")"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18Q_04",
        "category": "quantile-input-mean250",
        "idea": "Smooth INPUT with 250d mean then quantile.",
        "original": '-quantile(ts_mean(returns, 250), driver="gaussian")',
        "expression": (
            "-1 * quantile(ts_mean(returns, 250), driver=\"gaussian\")"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ18Q_05",
        "category": "quantile-winz-decay",
        "idea": "winsorize(-quantile,std=2) + ts_decay_linear 20.",
        "original": "ts_decay_linear(winsorize(-quantile, 2), 20)",
        "expression": (
            "ts_decay_linear(winsorize("
            "-1 * quantile(returns, driver=\"gaussian\"), std=2), 20)"
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
