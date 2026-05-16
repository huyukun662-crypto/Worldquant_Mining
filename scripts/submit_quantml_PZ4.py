"""QuantML PZ4: pure-PV, no mdl77/open/close, structurally different from PZ1-3.

PZ1-3 were all ts_corr / autocorr. PZ4 explores totally new operators:
range-position, zscore, rank, momentum reversal, and the three-stage
trade_when(group(ts_rank)) template from the BRAIN training doc.

  PZ4_01  Williams %R-style range position
          -((high - ts_min(low, 60)) / (ts_max(high, 60) - ts_min(low, 60)))
  PZ4_02  Range anomaly: -ts_zscore(high - low, 250)
  PZ4_03  Volume percentile reversal: -ts_rank(volume, 250)
  PZ4_04  VWAP momentum reversal: -ts_mean(vwap / ts_delay(vwap, 5) - 1, 60)
  PZ4_05  Three-stage trade_when(group(ts_rank)):
          trade_when(volume > ts_mean(volume, 60),
                     -ts_rank(high - low, 250), -1)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


SET_IND = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.05,
}
SET_IND_D2 = {
    "universe": "TOP3000", "decay": 2,
    "neutralization": "INDUSTRY", "truncation": 0.03,
}
SET_IND_D0 = {
    "universe": "TOP3000", "decay": 0,
    "neutralization": "INDUSTRY", "truncation": 0.05,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ4_01",
        "category": "williams-R-range-position",
        "idea": "Position of high in 60-day range (Williams %R-style).",
        "original": "-(high - ts_min(low,60)) / (ts_max(high,60) - ts_min(low,60))",
        "expression": (
            "-1 * (high - ts_min(low, 60)) / "
            "(ts_max(high, 60) - ts_min(low, 60))"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ4_02",
        "category": "range-zscore-anomaly",
        "idea": "Negative z-score of daily range over 250d.",
        "original": "-ts_zscore(high - low, 250)",
        "expression": "-1 * ts_zscore(high - low, 250)",
        "settings_override": SET_IND_D2,
    },
    {
        "id": "QM_PZ4_03",
        "category": "volume-rank-reversal",
        "idea": "Negative rolling rank of volume (high-volume names reversal).",
        "original": "-ts_rank(volume, 250)",
        "expression": "-1 * ts_rank(volume, 250)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ4_04",
        "category": "vwap-momentum-reversal",
        "idea": "Reversal on 5-day VWAP returns averaged over 60d.",
        "original": "-ts_mean(vwap/delay(vwap,5) - 1, 60)",
        "expression": "-1 * ts_mean(vwap / ts_delay(vwap, 5) - 1, 60)",
        "settings_override": SET_IND_D2,
    },
    {
        "id": "QM_PZ4_05",
        "category": "trade_when-rank-range",
        "idea": "Three-stage: gate on volume burst, signal=-ts_rank(range).",
        "original": "trade_when(vol>avg60, -ts_rank(HL,250), -1)",
        "expression": (
            "trade_when(volume > ts_mean(volume, 60), "
            "-1 * ts_rank(high - low, 250), -1)"
        ),
        "settings_override": SET_IND_D0,
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
