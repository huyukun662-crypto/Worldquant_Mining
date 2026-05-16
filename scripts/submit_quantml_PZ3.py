"""QuantML PZ3: continue pure-PV cross-corr family from PZ2.

PZ2 confirmed vwap autocorr + vwap×high cross-corr clean at SH 1.4-1.7.
PZ3 explores adjacent shapes:

  PZ3_01  ts_corr(vwap, low, 500)              vwap-low (vwap-high worked)
  PZ3_02  ts_corr(high, ts_delay(high, 5), 500) high autocorr
  PZ3_03  ts_corr(volume, ts_delay(volume, 5), 500) volume autocorr
  PZ3_04  ts_corr(vwap, ts_delay(vwap, 20), 500) longer-lag vwap autocorr
  PZ3_05  ts_corr(vwap, adv20, 500)            vwap × adv20 cross-corr
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


SET_IND = {
    "universe": "TOP3000", "decay": 2,
    "neutralization": "INDUSTRY", "truncation": 0.03,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ3_01",
        "category": "vwap-low-corr",
        "idea": "vwap vs low cross-corr W=500.",
        "original": "ts_corr(vwap, low, 500)",
        "expression": "ts_corr(vwap, low, 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ3_02",
        "category": "high-autocorr-5d",
        "idea": "high autocorr W=500 lag=5.",
        "original": "ts_corr(high, delay(high,5), 500)",
        "expression": "ts_corr(high, ts_delay(high, 5), 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ3_03",
        "category": "volume-autocorr-5d",
        "idea": "volume autocorr W=500 lag=5.",
        "original": "ts_corr(volume, delay(volume,5), 500)",
        "expression": "ts_corr(volume, ts_delay(volume, 5), 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ3_04",
        "category": "vwap-autocorr-20d",
        "idea": "vwap autocorr W=500 lag=20.",
        "original": "ts_corr(vwap, delay(vwap,20), 500)",
        "expression": "ts_corr(vwap, ts_delay(vwap, 20), 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ3_05",
        "category": "vwap-adv20-corr",
        "idea": "vwap vs adv20 cross-corr W=500.",
        "original": "ts_corr(vwap, adv20, 500)",
        "expression": "ts_corr(vwap, adv20, 500)",
        "settings_override": SET_IND,
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
