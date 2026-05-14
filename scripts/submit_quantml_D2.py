"""QuantML round D2: D1 sign-flips + 3 new obscure fields.

D1 results:
  D1_03 mdl77 Amihud illiq      SH=-0.62  -> long-illiq variant
  D1_05 competitor PageRank      SH=-0.63  -> long-PageRank variant
  D1_02 mdl77 deep-value pb      TIMEOUT
  D1_01, D1_04                   too weak (|SH|<0.4)

D2 lineup:
  D2_01  +Mean(mdl77_milliq, 60)              flipped D1_03
  D2_02  +rank(pv13_com_page_rank)            flipped D1_05
  D2_03  -mdl77_liquidityriskfactor_nlmktcap  small-cap factor (uc=1)
  D2_04  Mean(pv13_custretsig_retsig, 20)     supply-chain signal (uc=1148)
  D2_05  Mean(snt_buzz_ret_fast_d1, 60)       fast-decay social-buzz (uc=46)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_D2_01",
        "category": "mdl77-amihud-illiq-LONG",
        "idea": (
            "D1_03 flipped: long high-illiquidity names (Amihud "
            "premium). 60d smoothing. uc=34."
        ),
        "original": "Mean(mdl77_milliq, 60)",
        "expression": "ts_mean(mdl77_liquidityriskfactor_milliq, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D2_02",
        "category": "competitor-pagerank-LONG",
        "idea": (
            "D1_05 flipped: long high-PageRank (well-connected, central "
            "in competitor graph) names. uc=1138."
        ),
        "original": "Rank(pv13_com_page_rank)",
        "expression": "rank(pv13_com_page_rank)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D2_03",
        "category": "mdl77-small-cap-nlmktcap",
        "idea": (
            "Short ln(market cap) = long small-cap factor. uc=1. "
            "Classic SMB. Smoothed 60d."
        ),
        "original": "-Mean(nl_mktcap, 60)",
        "expression": (
            "-1 * ts_mean(mdl77_liquidityriskfactor_nlmktcap, 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D2_04",
        "category": "supply-chain-custret",
        "idea": (
            "20d mean of customer-return sign (pv13_custretsig_retsig). "
            "Supply-chain momentum: positive customer return -> positive "
            "supplier return drift. uc=1148."
        ),
        "original": "Mean(pv13_custretsig_retsig, 20)",
        "expression": "ts_mean(pv13_custretsig_retsig, 20)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D2_05",
        "category": "social-buzz-fast-decay",
        "idea": (
            "60d mean of snt_buzz_ret_fast_d1 -- fast-decay social-media "
            "negative buzz return signal. uc=46 (very obscure). "
            "Sign positive: long persistent negative-buzz-return names."
        ),
        "original": "Mean(snt_buzz_ret_fast_d1, 60)",
        "expression": "ts_mean(snt_buzz_ret_fast_d1, 60)",
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
