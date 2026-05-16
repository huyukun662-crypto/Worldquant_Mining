"""QuantML PZ10: push lag=20 + double-smooth + asymmetric cross.

  PZ10_01  ts_corr(high, ts_delay(high, 20), 500)        high autocorr lag=20
  PZ10_02  ts_corr(low, ts_delay(low, 20), 500)          low autocorr lag=20
  PZ10_03  ts_decay_linear(ts_corr(high, low, 2000), 20) smooth PZ8_01
  PZ10_04  ts_corr(vwap, ts_delay(high, 5), 500)         vwap vs lagged-high
  PZ10_05  ts_corr(high, vwap, 1000)                     extend vwap-high
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
        "id": "QM_PZ10_01",
        "category": "high-autocorr-20d",
        "idea": "high autocorr lag=20.",
        "original": "ts_corr(high, delay(high,20), 500)",
        "expression": "ts_corr(high, ts_delay(high, 20), 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ10_02",
        "category": "low-autocorr-20d",
        "idea": "low autocorr lag=20.",
        "original": "ts_corr(low, delay(low,20), 500)",
        "expression": "ts_corr(low, ts_delay(low, 20), 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ10_03",
        "category": "HL-corr-2000-smooth",
        "idea": "Smooth PZ8_01 (HL W=2000 SH 1.83) with decay 20.",
        "original": "ts_decay_linear(ts_corr(high, low, 2000), 20)",
        "expression": "ts_decay_linear(ts_corr(high, low, 2000), 20)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ10_04",
        "category": "vwap-lagged-high-corr",
        "idea": "Asymmetric: vwap vs 5-day-lagged high cross-corr.",
        "original": "ts_corr(vwap, delay(high,5), 500)",
        "expression": "ts_corr(vwap, ts_delay(high, 5), 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ10_05",
        "category": "vwap-high-corr-1000",
        "idea": "Extend vwap-high past 500 to 1000.",
        "original": "ts_corr(high, vwap, 1000)",
        "expression": "ts_corr(high, vwap, 1000)",
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
