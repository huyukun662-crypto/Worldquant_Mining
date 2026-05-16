"""QuantML PZ2: PV-only, no mdl77/open/close. Follow up on PZ1_03 hint.

PZ1_03 gave SH=-1.64 -- the signal is strong but we negated it wrong.
Drop the -1, that gives +1.64. Round explores nearby cross-corr shapes
on vwap/high/low/volume.

  PZ2_01  ts_corr(vwap, ts_delay(vwap, 5), 500)         (sign flipped)
  PZ2_02  ts_corr(vwap, ts_delay(vwap, 10), 500)        longer lag
  PZ2_03  ts_corr(vwap, ts_delay(vwap, 1), 500)         1-day lag
  PZ2_04  ts_corr(vwap, high, 500)                      vwap-high corr
  PZ2_05  ts_corr(low, volume, 500)                     low-volume corr
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
        "id": "QM_PZ2_01",
        "category": "vwap-autocorr-5d",
        "idea": "PZ1_03 sign-flipped: positive vwap autocorr W=500 lag=5.",
        "original": "ts_corr(vwap, delay(vwap,5), 500)",
        "expression": "ts_corr(vwap, ts_delay(vwap, 5), 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ2_02",
        "category": "vwap-autocorr-10d",
        "idea": "vwap autocorr W=500 lag=10.",
        "original": "ts_corr(vwap, delay(vwap,10), 500)",
        "expression": "ts_corr(vwap, ts_delay(vwap, 10), 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ2_03",
        "category": "vwap-autocorr-1d",
        "idea": "vwap autocorr W=500 lag=1.",
        "original": "ts_corr(vwap, delay(vwap,1), 500)",
        "expression": "ts_corr(vwap, ts_delay(vwap, 1), 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ2_04",
        "category": "vwap-high-corr",
        "idea": "vwap vs high cross-corr W=500.",
        "original": "ts_corr(vwap, high, 500)",
        "expression": "ts_corr(vwap, high, 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ2_05",
        "category": "low-volume-corr",
        "idea": "low vs volume cross-corr W=500.",
        "original": "ts_corr(low, volume, 500)",
        "expression": "ts_corr(low, volume, 500)",
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
