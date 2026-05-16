"""QuantML PZ11: smooth PZ10 winners + adv20 / vwap-low extensions.

  PZ11_01  ts_decay_linear(ts_corr(vwap, delay(high,5), 500), 20)  smooth PZ10_04
  PZ11_02  ts_decay_linear(ts_corr(vwap, low, 500), 20)            smooth PZ3_01
  PZ11_03  ts_corr(vwap, low, 1500)                                 extend further
  PZ11_04  ts_corr(adv20, high - low, 500)                          adv20 vs range
  PZ11_05  ts_corr(high, ts_delay(low, 10), 500)                    high vs lagged low (10d)
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
        "id": "QM_PZ11_01",
        "category": "vwap-lagged-high-smooth",
        "idea": "Smooth PZ10_04 (vwap vs delayed-high SH 1.78) with decay 20.",
        "original": "ts_decay_linear(ts_corr(vwap, delay(high,5), 500), 20)",
        "expression": (
            "ts_decay_linear(ts_corr(vwap, ts_delay(high, 5), 500), 20)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ11_02",
        "category": "vwap-low-smooth-500",
        "idea": "Smooth PZ3_01 (vwap-low W=500 SH 1.56) with decay 20.",
        "original": "ts_decay_linear(ts_corr(vwap, low, 500), 20)",
        "expression": "ts_decay_linear(ts_corr(vwap, low, 500), 20)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ11_03",
        "category": "vwap-low-corr-1500",
        "idea": "Extend vwap-low past 1000 to 1500.",
        "original": "ts_corr(vwap, low, 1500)",
        "expression": "ts_corr(vwap, low, 1500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ11_04",
        "category": "adv20-range-corr",
        "idea": "adv20 vs daily range cross-corr W=500.",
        "original": "ts_corr(adv20, high-low, 500)",
        "expression": "ts_corr(adv20, high - low, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ11_05",
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
