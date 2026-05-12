"""QuantML round F1: fundamental + alternative data factors.

All prior factors were price-volume only. This round taps:
  Model (composite fundamental ratios) - value/quality/investment
  Social Media (sentiment z-score)

Each factor uses a DIFFERENT economic source from the others AND
from all 7 prior viables:

  F1_01  Value         forward_book_value_to_price            (Model)
  F1_02  Quality       gross_profit_to_assets_ratio (Novy-Marx) (Model)
  F1_03  Investment    -capex_to_total_assets (FF5 CMA)       (Model)
  F1_04  Earnings yld  forward_ebitda_to_enterprise_value_2   (Model)
  F1_05  Sentiment     ts_mean(snt_social_value, 20)          (SocialMedia)

Fundamental ratios update quarterly so TO should be naturally low.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_F1_01",
        "category": "fund-value",
        "idea": (
            "Classic Fama-French value: book value / price. The "
            "forward (analyst-estimated) version captures forward-"
            "looking value premium. Long high B/P (cheap names)."
        ),
        "original": "forward_book_value_to_price",
        "expression": "forward_book_value_to_price",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_F1_02",
        "category": "fund-quality",
        "idea": (
            "Novy-Marx gross profitability: TTM gross profit / total "
            "assets. Long high-GP/A (efficient asset use); robust "
            "anomaly across markets."
        ),
        "original": "gross_profit_to_assets_ratio",
        "expression": "gross_profit_to_assets_ratio",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_F1_03",
        "category": "fund-investment-cma",
        "idea": (
            "FF5 conservative-minus-aggressive (CMA): low-capex "
            "names outperform. Short high capex_to_total_assets."
        ),
        "original": "-capex_to_total_assets",
        "expression": "-1 * capex_to_total_assets",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_F1_04",
        "category": "fund-earnings-yield",
        "idea": (
            "Forward EBITDA / enterprise value -- EBITDA yield, "
            "cousin of E/P controlling for capital structure. Long "
            "high yield (cheap names)."
        ),
        "original": "forward_ebitda_to_enterprise_value_2",
        "expression": "forward_ebitda_to_enterprise_value_2",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_F1_05",
        "category": "alt-sentiment",
        "idea": (
            "20-day mean of social-media sentiment z-score "
            "(snt_social_value). Long persistent positive "
            "sentiment. Pure alternative-data signal."
        ),
        "original": "Mean(snt_social_value, 20)",
        "expression": "ts_mean(snt_social_value, 20)",
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
