"""QuantML PZ8: HL corr ultra-long + smooth wrappers on PZ winners.

  PZ8_01  ts_corr(high, low, 2000)                       extend past 1500
  PZ8_02  ts_decay_linear(ts_corr(high, low, 1000), 20)  smooth PZ6_01
  PZ8_03  ts_decay_linear(ts_corr(low, delay(low,5), 500), 20)  smooth PZ7_01
  PZ8_04  ts_corr(vwap, low, 750)                        extend vwap-low
  PZ8_05  ts_corr(vwap, high, 250)                       short vwap-high
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
        "id": "QM_PZ8_01",
        "category": "HL-corr-2000",
        "idea": "Even longer window than 1500.",
        "original": "ts_corr(high, low, 2000)",
        "expression": "ts_corr(high, low, 2000)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ8_02",
        "category": "HL-corr-1000-smooth",
        "idea": "Smooth PZ6_01 (SH 1.91) with decay 20.",
        "original": "ts_decay_linear(ts_corr(high, low, 1000), 20)",
        "expression": "ts_decay_linear(ts_corr(high, low, 1000), 20)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ8_03",
        "category": "low-autocorr-5d-smooth",
        "idea": "Smooth PZ7_01 (SH 1.52) low autocorr with decay 20.",
        "original": "ts_decay_linear(ts_corr(low, delay(low,5), 500), 20)",
        "expression": (
            "ts_decay_linear(ts_corr(low, ts_delay(low, 5), 500), 20)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ8_04",
        "category": "vwap-low-corr-750",
        "idea": "Extend vwap-low (clean at W=500) to W=750.",
        "original": "ts_corr(vwap, low, 750)",
        "expression": "ts_corr(vwap, low, 750)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ8_05",
        "category": "vwap-high-corr-250",
        "idea": "Short window vwap-high (clean at W=500).",
        "original": "ts_corr(vwap, high, 250)",
        "expression": "ts_corr(vwap, high, 250)",
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
