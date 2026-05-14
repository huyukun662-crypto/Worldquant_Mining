"""QuantML round D4: operator variants on obscure-field winners.

D1+D2+D3 evidence (10 obscure-field factors tested):
  Best 4 raw SH:  D2_02 PageRank LONG 0.63 | D3_04 illiq W250 0.64 |
                  D2_01 illiq 60d 0.62    | D3_03 supply-chain LONG 0.53
  All composites diluted (rank 0.24, zscore 0.35).
  Long-window recipe gave only +0.02 SH.

Hypothesis: obscure fields cap at SH<0.7 on simple smoothing -- they
encode slow-moving information. To break SH>1.75, try OPERATORS not
yet applied (variance, delta, correlation, cross-stock dispersion).

D4 lineup:
  D4_01  ts_std_dev(illiq, 250) -- illiquidity VOLATILITY (not level)
  D4_02  ts_delta(illiq, 60)/illiq -- relative change of illiq (60d)
  D4_03  ts_corr(pv13_com_page_rank, volume, 60) -- crowd-volume link
  D4_04  earnings_expectation_module (mdl77, uc=1, untested)
  D4_05  earnings_quality_module     (mdl77, uc=1, untested)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_D4_01",
        "category": "illiq-volatility",
        "idea": (
            "ts_std_dev of Amihud illiquidity over 250d. Captures "
            "illiquidity instability -- stocks whose liquidity regime "
            "changes (a different signal than illiquidity LEVEL)."
        ),
        "original": "Std(milliq, 250)",
        "expression": (
            "ts_std_dev(mdl77_liquidityriskfactor_milliq, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 2,
            "neutralization": "INDUSTRY",
            "truncation": 0.03,
        },
    },
    {
        "id": "QM_D4_02",
        "category": "illiq-relative-change",
        "idea": (
            "60d relative change in Amihud illiquidity. Rising illiq = "
            "drying liquidity -- sign negative: short drying-liq names."
        ),
        "original": "-Delta(milliq, 60)/milliq",
        "expression": (
            "-1 * ts_delta(mdl77_liquidityriskfactor_milliq, 60) / "
            "mdl77_liquidityriskfactor_milliq"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D4_03",
        "category": "pagerank-volume-corr",
        "idea": (
            "60d ts_corr(PageRank, volume). PageRank is slow-moving so "
            "this is essentially the average volume of central names. "
            "Hybrid: graph centrality x trading activity."
        ),
        "original": "Corr(pagerank, volume, 60)",
        "expression": "ts_corr(pv13_com_page_rank, volume, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D4_04",
        "category": "earnings-expectation-module",
        "idea": (
            "mdl77 earnings-expectation module raw value. uc=1 -- "
            "essentially untested by anyone. Smoothed 60d."
        ),
        "original": "Mean(eem, 60)",
        "expression": (
            "ts_mean("
            "mdl77_2valuemomemtummodel_earningsexpectationmodule, 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D4_05",
        "category": "earnings-quality-module",
        "idea": (
            "mdl77 earnings-quality module raw value. uc=1 -- "
            "essentially untested. Smoothed 60d."
        ),
        "original": "Mean(eqm, 60)",
        "expression": (
            "ts_mean("
            "mdl77_2valuemomemtummodel_earningsqualitymodule, 60)"
        ),
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
