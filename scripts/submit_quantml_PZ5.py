"""QuantML PZ5: rescue PZ4_04 (vwap momentum reversal, SH 1.02 just under gate).

PZ4_04: -ts_mean(vwap/delay(vwap,5)-1, 60) SH 1.02 FIT 1.28 -- gate 1.25.
Multiple variants: longer lags, longer windows, winsorize wrap, decay.

  PZ5_01  -ts_mean(vwap/delay(vwap,10)-1, 100)  longer lag + window
  PZ5_02  -ts_mean(vwap/delay(vwap,20)-1, 250)  monthly reversal
  PZ5_03  ts_decay_linear(-ts_mean(vwap/delay(vwap,5)-1, 60), 20)  smoothed
  PZ5_04  winsorize(-ts_mean(vwap/delay(vwap,5)-1, 60), std=3)     winz
  PZ5_05  -ts_mean(vwap/delay(vwap,60)-1, 250)  long-term reversal
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
SET_T05 = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.05,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ5_01",
        "category": "vwap-rev-10d-100w",
        "idea": "Longer lag (10d) and avg window (100d).",
        "original": "-ts_mean(vwap/delay(vwap,10)-1, 100)",
        "expression": "-1 * ts_mean(vwap / ts_delay(vwap, 10) - 1, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ5_02",
        "category": "vwap-rev-20d-250w",
        "idea": "Monthly lag (20d), long avg (250d).",
        "original": "-ts_mean(vwap/delay(vwap,20)-1, 250)",
        "expression": "-1 * ts_mean(vwap / ts_delay(vwap, 20) - 1, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ5_03",
        "category": "vwap-rev-decay-smooth",
        "idea": "PZ4_04 base wrapped in ts_decay_linear(., 20).",
        "original": "ts_decay_linear(-ts_mean(vwap/delay(vwap,5)-1, 60), 20)",
        "expression": (
            "ts_decay_linear(-1 * ts_mean(vwap / ts_delay(vwap, 5) - 1, 60), 20)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_PZ5_04",
        "category": "vwap-rev-winz",
        "idea": "PZ4_04 base wrapped in winsorize std=3.",
        "original": "winsorize(-ts_mean(vwap/delay(vwap,5)-1, 60), std=3)",
        "expression": (
            "winsorize(-1 * ts_mean(vwap / ts_delay(vwap, 5) - 1, 60), std=3)"
        ),
        "settings_override": SET_T05,
    },
    {
        "id": "QM_PZ5_05",
        "category": "vwap-rev-60d-250w",
        "idea": "Quarter lag (60d), long avg (250d) -- long-term reversal.",
        "original": "-ts_mean(vwap/delay(vwap,60)-1, 250)",
        "expression": "-1 * ts_mean(vwap / ts_delay(vwap, 60) - 1, 250)",
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
