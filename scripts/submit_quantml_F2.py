"""QuantML round F2: fundamental/alternative factors (accessible-field rerun).

F1's Model-category fields (forward_book_value_to_price, gross_profit_
to_assets_ratio etc.) errored as "Invalid data field" on this tier.
Switch to Analyst/Option/Sentiment fields confirmed accessible (high
alphaCount in community use).

  F2_01  Option IV regime    ts_mean(implied_volatility_call_270, 60)
                              -- 270d call IV smoothed; vol-risk premium
  F2_02  Put-Call ratio      pcr_oi_270 -- open-interest fear gauge
  F2_03  Analyst revision    anl4_adjusted_netincome_ft -- net income flag
  F2_04  Earnings surprise   snt1_d1_earningssurprise -- sentiment signal
  F2_05  EBITDA delta        ts_delta(anl4_ebitda_value, 60) -- forecast
                              momentum over 60d
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_F2_01",
        "category": "opt-iv-regime",
        "idea": (
            "60-day mean of 270-day call implied volatility. Captures "
            "persistent option-market vol regime. Long high-IV names "
            "(vol risk premium)."
        ),
        "original": "Mean(implied_volatility_call_270, 60)",
        "expression": "ts_mean(implied_volatility_call_270, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_F2_02",
        "category": "opt-pcr",
        "idea": (
            "270-day put-call open-interest ratio. High PCR = fear / "
            "hedging demand = contrarian buy signal. Long high PCR."
        ),
        "original": "pcr_oi_270",
        "expression": "pcr_oi_270",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_F2_03",
        "category": "anl-revision",
        "idea": (
            "Analyst adjusted-net-income forecast revision flag "
            "(anl4_adjusted_netincome_ft). Positive = upward revision. "
            "Long positive revisions (revision momentum)."
        ),
        "original": "anl4_adjusted_netincome_ft",
        "expression": "anl4_adjusted_netincome_ft",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_F2_04",
        "category": "snt-earnings-surprise",
        "idea": (
            "snt1 earnings surprise sentiment score. Long positive "
            "surprise (post-earnings-announcement drift)."
        ),
        "original": "snt1_d1_earningssurprise",
        "expression": "snt1_d1_earningssurprise",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_F2_05",
        "category": "anl-ebitda-momentum",
        "idea": (
            "60-day change in anl4_ebitda_value forecast. Captures "
            "analyst EBITDA estimate momentum. Long positive momentum."
        ),
        "original": "Delta(anl4_ebitda_value, 60)",
        "expression": "ts_delta(anl4_ebitda_value, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
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
