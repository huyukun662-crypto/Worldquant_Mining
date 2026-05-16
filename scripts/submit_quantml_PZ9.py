"""QuantML PZ9: smooth winners + extend lag/window edges.

  PZ9_01  ts_decay_linear(ts_corr(high, low, 1500), 20)   smooth PZ7_04
  PZ9_02  ts_decay_linear(ts_corr(vwap, delay(vwap,10), 500), 20)  smooth PZ2_02
  PZ9_03  ts_corr(vwap, low, 1000)                        extend vwap-low past 750
  PZ9_04  ts_corr(high, ts_delay(high, 10), 500)          high autocorr lag=10
  PZ9_05  ts_corr(low, ts_delay(low, 10), 500)            low autocorr lag=10
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
        "id": "QM_PZ9_01",
        "category": "HL-corr-1500-smooth",
        "idea": "Smooth PZ7_04 (HL W=1500 SH 1.85) with decay 20.",
        "original": "ts_decay_linear(ts_corr(high, low, 1500), 20)",
        "expression": "ts_decay_linear(ts_corr(high, low, 1500), 20)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ9_02",
        "category": "vwap-autocorr-10d-smooth",
        "idea": "Smooth PZ2_02 (vwap autocorr 10d, SH 1.73) with decay 20.",
        "original": "ts_decay_linear(ts_corr(vwap, delay(vwap,10), 500), 20)",
        "expression": (
            "ts_decay_linear(ts_corr(vwap, ts_delay(vwap, 10), 500), 20)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ9_03",
        "category": "vwap-low-corr-1000",
        "idea": "Extend vwap-low past 750.",
        "original": "ts_corr(vwap, low, 1000)",
        "expression": "ts_corr(vwap, low, 1000)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ9_04",
        "category": "high-autocorr-10d",
        "idea": "high autocorr W=500 lag=10.",
        "original": "ts_corr(high, delay(high,10), 500)",
        "expression": "ts_corr(high, ts_delay(high, 10), 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ9_05",
        "category": "low-autocorr-10d",
        "idea": "low autocorr W=500 lag=10.",
        "original": "ts_corr(low, delay(low,10), 500)",
        "expression": "ts_corr(low, ts_delay(low, 10), 500)",
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
