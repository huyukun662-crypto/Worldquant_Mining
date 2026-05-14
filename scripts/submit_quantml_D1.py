"""QuantML round D1: obscure data-fields — orthogonal to 4 existing OHLC-PV families.

Mined from data_fields_cache_USA_1_TOP3000.json (vendored upstream miner).
Hand-picked for LOW userCount (most are uc<=50, several uc=1) so the
resulting alphas are unlikely to overlap submission-wise with existing
viables R6_01 / N3 / X5 / Z4 (all pure OHLC PV).

  D1_01  analyst guidance width
            (max_ebitda_guidance - min_ebitda_guidance) / abs(min)
            -- captures forecast dispersion at the company-issued level
            (totally orthogonal to price-action factors). uc=14/24.
  D1_02  mdl77 deep-value smoothed book-to-market
            ts_mean(mdl77_deepvaluefactor_pb, 60). uc=1.
  D1_03  mdl77 Amihud-style illiquidity smoothed
            -1 * ts_mean(mdl77_liquidityriskfactor_milliq, 60). uc=34.
            Sign negative: short high-illiquidity names (size-like).
  D1_04  news-post 30-min response mean
            ts_mean(news_pct_30min, 60). uc=327. Event-day price reaction
            averaged -- a behavioural signal.
  D1_05  competitor-PageRank rank
            -1 * rank(pv13_com_page_rank). uc=1138. Cross-stock graph
            position; short well-connected names (crowded).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_D1_01",
        "category": "analyst-guidance-width",
        "idea": (
            "EBITDA analyst guidance width: (max - min) / |min|. "
            "Forecast dispersion at the company level. Sign negative: "
            "short high-dispersion names (uncertainty premium)."
        ),
        "original": "-(max_ebitda - min_ebitda) / |min_ebitda|",
        "expression": (
            "-1 * (max_ebitda_guidance - min_ebitda_guidance) / "
            "abs(min_ebitda_guidance)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D1_02",
        "category": "mdl77-deep-value-pb",
        "idea": (
            "mdl77 deep-value book/market smoothed 60d. Classic value: "
            "long cheap names. uc=1 -- effectively undiscovered."
        ),
        "original": "Mean(mdl77_pb, 60)",
        "expression": "ts_mean(mdl77_deepvaluefactor_pb, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D1_03",
        "category": "mdl77-amihud-illiquidity",
        "idea": (
            "mdl77 Amihud illiquidity smoothed 60d. Short high-illiquidity "
            "(size-like factor). uc=34."
        ),
        "original": "-Mean(mdl77_milliq, 60)",
        "expression": "-1 * ts_mean(mdl77_liquidityriskfactor_milliq, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D1_04",
        "category": "news-30min-response",
        "idea": (
            "60d mean of news-post 30-min %change. Behavioural event "
            "response signal. uc=327. Sign positive: long names that "
            "react positively to news (drift)."
        ),
        "original": "Mean(news_pct_30min, 60)",
        "expression": "ts_mean(news_pct_30min, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D1_05",
        "category": "competitor-pagerank",
        "idea": (
            "Cross-sectional rank of competitor-graph PageRank, sign "
            "flipped: short central / well-connected names (crowded "
            "market position). uc=1138."
        ),
        "original": "-Rank(pv13_com_page_rank)",
        "expression": "-1 * rank(pv13_com_page_rank)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
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
