"""QuantML round D16: explore Family F (ts_corr) / G (group-agg) / H (rank).

D1-D15: every viable from the obscure-datafield push is a multiplicative
CoV-blend variant (Family E). To deliver structurally NEW families on
obscure fields, D16 tests 5 candidate skeletons:

  D16_01 Family F  -ts_corr(milliq, volume, 60)
         Illiquidity-volume coupling (60d). Rising illiq while volume
         falls = panic-illiquidity. Time-series correlation, not the
         second moment of a single field.

  D16_02 Family F  -ts_corr(milliq, returns, 60)
         Direct illiquidity-return coupling -- when illiq moves with
         returns, the stock has illiq-driven price action.

  D16_03 Family G  -ts_std_dev(group_mean(milliq, 1, subindustry), 60)
         Volatility of industry-average illiquidity. Group-aggregate
         dynamics, not stock-level dynamics.

  D16_04 Family H  -rank(ts_std_dev(milliq, 100))
         Pure cross-sectional ranking of single-stock illiq vol.
         Distinct from CoV (which is std/mean and uses neutralization
         to handle the cross-section).

  D16_05 Family F  -ts_corr(milliq, bap20d, 60) but @ truncation=0.10
         D13_01 was at 0.05; retry with looser truncation since
         peer-distance Family D was lifted by t=0.10.

All @ SUBINDUSTRY decay=4 trunc=0.05 (except D16_05 @ 0.10).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP20D = "mdl77_liquidityriskfactor_bap20d"

SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D16_01",
        "category": "milliq-volume-corr",
        "idea": (
            "Family F prototype: ts_corr(milliq, volume, 60). When "
            "illiquidity rises while volume falls -> panic-illiquidity."
        ),
        "original": "-ts_corr(milliq, volume, 60)",
        "expression": f"-1 * ts_corr({MILLIQ}, volume, 60)",
        "settings_override": SET,
    },
    {
        "id": "QM_D16_02",
        "category": "milliq-returns-corr",
        "idea": (
            "Family F: ts_corr(milliq, returns, 60). Tests illiq-driven "
            "price action vs flow-driven."
        ),
        "original": "-ts_corr(milliq, returns, 60)",
        "expression": f"-1 * ts_corr({MILLIQ}, returns, 60)",
        "settings_override": SET,
    },
    {
        "id": "QM_D16_03",
        "category": "industry-illiq-vol",
        "idea": (
            "Family G: volatility of industry-average illiquidity. "
            "Captures industry-level liquidity-regime instability."
        ),
        "original": "-Std(group_mean(milliq, subindustry), 60)",
        "expression": (
            f"-1 * ts_std_dev(group_mean({MILLIQ}, 1, subindustry), 60)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D16_04",
        "category": "illiq-vol-rank",
        "idea": (
            "Family H: cross-sectional rank of single-stock illiq vol. "
            "Pure ranking signal, no second-moment structure."
        ),
        "original": "-rank(Std(milliq, 100))",
        "expression": f"-1 * rank(ts_std_dev({MILLIQ}, 100))",
        "settings_override": SET,
    },
    {
        "id": "QM_D16_05",
        "category": "milliq-bap20d-corr-t10",
        "idea": (
            "D13_01 retry: ts_corr(milliq, bap20d, 60) at truncation=0.10 "
            "(D13 was at 0.05). Family D pattern: looser trunc lifted "
            "peer-distance from 1.06 to 1.34."
        ),
        "original": "-ts_corr(milliq, bap20d, 60) t=0.10",
        "expression": f"-1 * ts_corr({MILLIQ}, {BAP20D}, 60)",
        "settings_override": {**SET, "truncation": 0.10},
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
