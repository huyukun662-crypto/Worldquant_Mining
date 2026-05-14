"""QuantML round D3: cross-source composite + D2 sign flips + variants.

D2 yielded 3 clean directional signals from genuinely orthogonal data
sources (uncorrelated by construction -- different categories entirely):

  D2_01 mdl77 Amihud illiq LONG     SH=0.62  (model fundamental)
  D2_02 PageRank LONG               SH=0.63  (graph relationship)
  D2_03 small-cap nlmktcap          SH=0.45  (model fundamental)

Composite of these may exceed 1.3 (cross-source diversification).
D2_04 supply-chain has SH=-0.68 -- flip is the obvious test.

D3 lineup:
  D3_01  rank composite of the 3 winners (illiq + pagerank + smcap)
  D3_02  z-score composite of the 3 winners
  D3_03  D2_04 sign-flipped: supply-chain custret LONG (60d window)
  D3_04  D2_01 with longer window: ts_mean(milliq, 250)
  D3_05  pv13_ompetitorgraphrank_hub_rank LONG (HITS hub centrality,
         uc=863, distinct from PageRank by graph theory)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

# Three D2 winner components, all aligned LONG
ILLIQ = "ts_mean(mdl77_liquidityriskfactor_milliq, 60)"
PAGERANK = "rank(pv13_com_page_rank)"
SMCAP = "-1 * ts_mean(mdl77_liquidityriskfactor_nlmktcap, 60)"


FACTORS: list[dict] = [
    {
        "id": "QM_D3_01",
        "category": "cross-source-rank-composite",
        "idea": (
            "Rank composite of 3 D2 winners from 3 orthogonal data "
            "sources: Amihud illiq + competitor PageRank + small-cap. "
            "Different categories means low correlation -- the standard "
            "objection to composites (within-family dilution) does not "
            "apply here."
        ),
        "original": "rank(illiq)+rank(pagerank)+rank(smcap)",
        "expression": (
            f"rank({ILLIQ}) + rank({PAGERANK}) + rank({SMCAP})"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D3_02",
        "category": "cross-source-zscore-composite",
        "idea": (
            "Z-score composite of 3 D2 winners. Same idea as D3_01 but "
            "z-score normalisation may handle scale better."
        ),
        "original": "zscore(illiq)+zscore(pagerank)+zscore(smcap)",
        "expression": (
            f"zscore({ILLIQ}) + zscore({PAGERANK}) + zscore({SMCAP})"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D3_03",
        "category": "supply-chain-custret-LONG",
        "idea": (
            "D2_04 sign-flipped: long supply-chain custret signal. "
            "D2_04 was SH=-0.68, the flip should be +0.68. TO was high "
            "(0.19) so try shorter window for cleaner signal."
        ),
        "original": "-Mean(custret, 20)",
        "expression": "-1 * ts_mean(pv13_custretsig_retsig, 20)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D3_04",
        "category": "mdl77-amihud-illiq-W250",
        "idea": (
            "D2_01 with 250d window (vs 60d). The winning recipe on "
            "PV factors was W250-W500 + decay=2; try it on illiq."
        ),
        "original": "Mean(milliq, 250)",
        "expression": (
            "ts_mean(mdl77_liquidityriskfactor_milliq, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 2,
            "neutralization": "INDUSTRY",
            "truncation": 0.03,
        },
    },
    {
        "id": "QM_D3_05",
        "category": "hits-hub-rank",
        "idea": (
            "Competitor-graph HITS hub centrality (distinct from "
            "PageRank: hubs link to authorities, authorities link to "
            "hubs). uc=863. Try LONG."
        ),
        "original": "Rank(hub_rank)",
        "expression": "rank(pv13_ompetitorgraphrank_hub_rank)",
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
