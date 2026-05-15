"""QuantML round D14: variance-shape on cross-category obscure fields.

D13 confirmed only variance-class shapes (ts_std_dev, CoV) carry signal
on milliq. D14 tests whether the same principle (variance-instability)
ports across data-field CATEGORIES -- different categories may
contribute uncorrelated alpha.

  D14_01 -ts_std_dev(snt_buzz, 100)            socialmedia   uc=4
  D14_02 -ts_std_dev(max_ebitda_guidance, 100) analyst       uc=14
  D14_03 -ts_std_dev(news_indx_perf, 100)      news          uc=?
  D14_04 -ts_std_dev(scl12_sentiment, 100)     socialmedia   uc=4
  D14_05 -CoV(milliq,100) * ts_std_dev(snt_buzz,100)
         cross-category interaction: illiq instability x sentiment
         buzz volatility. If the multiplicative-blend trick from D10_05
         is structural (not field-specific), this should clear the
         gate -- and would be a structurally NEW family because it
         crosses categories.

All @ SUBINDUSTRY decay=4 trunc=0.05 (Family E sweet-spot).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"

SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D14_01",
        "category": "snt_buzz-std",
        "idea": "Volatility of sentiment buzz volume -- attention-instability.",
        "original": "-ts_std_dev(snt_buzz,100)",
        "expression": "-1 * ts_std_dev(snt_buzz, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D14_02",
        "category": "ebitda-guidance-std",
        "idea": "Volatility of max-EBITDA analyst guidance -- guidance dispersion.",
        "original": "-ts_std_dev(max_ebitda_guidance,100)",
        "expression": "-1 * ts_std_dev(max_ebitda_guidance, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D14_03",
        "category": "news_indx_perf-std",
        "idea": "Volatility of news-day stock-vs-SPX relative return.",
        "original": "-ts_std_dev(news_indx_perf,100)",
        "expression": "-1 * ts_std_dev(news_indx_perf, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D14_04",
        "category": "scl12_sentiment-std",
        "idea": "Volatility of social-sentiment score.",
        "original": "-ts_std_dev(scl12_sentiment,100)",
        "expression": "-1 * ts_std_dev(scl12_sentiment, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D14_05",
        "category": "illiq-CoV-x-sentiment-std",
        "idea": (
            "Cross-CATEGORY multiplicative blend: liquidity-risk x "
            "social-media. If the blend trick is structural rather than "
            "field-specific, this should clear the gate and represent a "
            "structurally NEW family (not just Family E variant)."
        ),
        "original": "-CoV(milliq,100)*Std(snt_buzz,100)",
        "expression": (
            f"-1 * ts_std_dev({MILLIQ}, 100) / ts_mean({MILLIQ}, 100) "
            f"* ts_std_dev(snt_buzz, 100)"
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
