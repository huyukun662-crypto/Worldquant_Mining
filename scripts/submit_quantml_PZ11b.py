"""QuantML PZ11b: re-run the 2 PZ11 candidates that did not complete.

  PZ11b_04  ts_corr(adv20, high - low, 500)              adv20 vs range
  PZ11b_05  ts_corr(high, ts_delay(low, 10), 500)        high vs lagged low 10d
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


SET = {
    "universe": "TOP3000", "decay": 2,
    "neutralization": "INDUSTRY", "truncation": 0.03,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ11b_04",
        "category": "adv20-range-corr",
        "idea": "adv20 vs daily range cross-corr W=500.",
        "original": "ts_corr(adv20, high-low, 500)",
        "expression": "ts_corr(adv20, high - low, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ11b_05",
        "category": "high-vs-lagged-low-10d",
        "idea": "high vs 10-day-lagged low cross-corr W=500.",
        "original": "ts_corr(high, delay(low, 10), 500)",
        "expression": "ts_corr(high, ts_delay(low, 10), 500)",
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
