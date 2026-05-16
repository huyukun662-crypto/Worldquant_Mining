"""QuantML PZ6: stay in proven ts_corr PV family, extend boundaries.

Clean ts_corr alphas we already have: high/low W=250..750, vwap autocorr,
vwap-high/low cross. Extend along underexplored axes.

  PZ6_01  ts_corr(high, low, 1000)              very-long window
  PZ6_02  ts_corr(high, low, 200)               short window
  PZ6_03  ts_corr(vwap, delay(vwap, 250), 500)  1-yr lag autocorr
  PZ6_04  ts_decay_linear(ts_corr(high, low, 500), 20)  smoothed corr
  PZ6_05  ts_corr(high, delay(low, 5), 500)     high vs lagged low
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
        "id": "QM_PZ6_01",
        "category": "HL-corr-1000",
        "idea": "ts_corr(high, low, 1000) -- extend beyond 750.",
        "original": "ts_corr(high, low, 1000)",
        "expression": "ts_corr(high, low, 1000)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ6_02",
        "category": "HL-corr-200",
        "idea": "ts_corr(high, low, 200) -- shorter than the 250 clean entry.",
        "original": "ts_corr(high, low, 200)",
        "expression": "ts_corr(high, low, 200)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ6_03",
        "category": "vwap-autocorr-250d",
        "idea": "vwap autocorr W=500 lag=250 (year-over-year mean reversion).",
        "original": "ts_corr(vwap, delay(vwap, 250), 500)",
        "expression": "ts_corr(vwap, ts_delay(vwap, 250), 500)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ6_04",
        "category": "HL-corr-500-smooth",
        "idea": "Smooth HL corr W=500 with 20-day decay.",
        "original": "ts_decay_linear(ts_corr(high, low, 500), 20)",
        "expression": "ts_decay_linear(ts_corr(high, low, 500), 20)",
        "settings_override": SET,
    },
    {
        "id": "QM_PZ6_05",
        "category": "high-lagged-low-corr",
        "idea": "Asymmetric: high vs 5-day-lagged low cross-corr W=500.",
        "original": "ts_corr(high, delay(low, 5), 500)",
        "expression": "ts_corr(high, ts_delay(low, 5), 500)",
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
