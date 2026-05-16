"""QuantML PZ7: more ts_corr PV variants.

  PZ7_01  ts_corr(low, ts_delay(low, 5), 500)        low autocorr (mirror of high)
  PZ7_02  ts_corr(vwap, volume, 500)                 vwap-volume cross
  PZ7_03  ts_corr(high - low, volume, 500)           range vs volume
  PZ7_04  ts_corr(high, low, 1500)                   ultra-long window
  PZ7_05  ts_decay_linear(ts_corr(high, delay(high, 5), 500), 20)  smooth PZ3_02
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
        "id": "QM_PZ7_01",
        "category": "low-autocorr-5d",
        "idea": "Low autocorr W=500 lag=5 (mirror of clean PZ3_02 high autocorr).",
        "original": "ts_corr(low, delay(low,5), 500)",
        "expression": "ts_corr(low, ts_delay(low, 5), 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ7_02",
        "category": "vwap-volume-corr",
        "idea": "vwap vs volume cross-corr W=500.",
        "original": "ts_corr(vwap, volume, 500)",
        "expression": "ts_corr(vwap, volume, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ7_03",
        "category": "range-volume-corr",
        "idea": "Daily range vs volume W=500.",
        "original": "ts_corr(high-low, volume, 500)",
        "expression": "ts_corr(high - low, volume, 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ7_04",
        "category": "HL-corr-1500",
        "idea": "ts_corr(high, low, 1500) -- extend past 1000.",
        "original": "ts_corr(high, low, 1500)",
        "expression": "ts_corr(high, low, 1500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ7_05",
        "category": "high-autocorr-5d-smooth",
        "idea": "ts_decay_linear smooth of clean PZ3_02 high autocorr 5d 500.",
        "original": "ts_decay_linear(ts_corr(high, delay(high,5), 500), 20)",
        "expression": (
            "ts_decay_linear(ts_corr(high, ts_delay(high, 5), 500), 20)"
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
