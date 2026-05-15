"""QuantML round D13: 5 structurally-distinct shapes on obscure mdl77 fields.

D1-D12 thoroughly explored the CoV (ts_std_dev/ts_mean) shape and its
multiplicative blend on liquidity-risk fields. Family E delivered 4
viables, but all are setting variants of one structure.

D13 tries 5 genuinely different shape categories on the same obscure
field universe:

  D13_01 ts_corr(milliq, bap20d, 60)
         co-movement of two illiquidity measures.
         Reversal logic: when illiq measures decouple, alpha exists.

  D13_02 ts_std_dev(ts_rank(milliq, 250), 60)
         rank-volatility: how stable is the cross-sectional illiquidity
         ranking? unstable -> reversion candidate.

  D13_03 -ts_delta(ts_delta(milliq, 20), 20)
         acceleration of illiquidity (second derivative). Negative sign
         because rising illiquidity should be a sell signal in slow
         regimes.

  D13_04 (ts_max(milliq, 60) - ts_min(milliq, 60)) / ts_mean(milliq, 60)
         range-to-mean ratio: scale-free illiquidity range.
         Different from CoV (uses max-min instead of std).

  D13_05 -ts_mean(milliq * volume, 60) / ts_mean(volume, 60)
         volume-weighted illiquidity mean. Volume IS allowed -- the
         spec only forbids reusing the OHLC-PV factor templates, not
         all PV fields. This is a new structural family combining
         obscure field with volume.

All @ SUBINDUSTRY decay=4 trunc=0.05 (the Family E sweet-spot).
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
        "id": "QM_D13_01",
        "category": "milliq-bap20d-corr",
        "idea": (
            "Rolling correlation of two illiquidity measures. When "
            "milliq and bap20d decouple (low/neg corr), a regime "
            "change is implied. Sign negative so low-corr -> long."
        ),
        "original": "-ts_corr(milliq, bap20d, 60)",
        "expression": f"-1 * ts_corr({MILLIQ}, {BAP20D}, 60)",
        "settings_override": SET,
    },
    {
        "id": "QM_D13_02",
        "category": "milliq-rank-volatility",
        "idea": (
            "Volatility of the cross-sectional illiquidity rank. "
            "Stocks whose illiquidity rank is unstable are subject "
            "to liquidity-regime mean-reversion."
        ),
        "original": "-ts_std_dev(ts_rank(milliq, 250), 60)",
        "expression": f"-1 * ts_std_dev(ts_rank({MILLIQ}, 250), 60)",
        "settings_override": SET,
    },
    {
        "id": "QM_D13_03",
        "category": "milliq-acceleration",
        "idea": (
            "Acceleration of illiquidity: second time-derivative. "
            "Captures regime-change inflection points rather than "
            "level or first-order change."
        ),
        "original": "-ts_delta(ts_delta(milliq,20),20)",
        "expression": f"-1 * ts_delta(ts_delta({MILLIQ}, 20), 20)",
        "settings_override": SET,
    },
    {
        "id": "QM_D13_04",
        "category": "milliq-range-to-mean",
        "idea": (
            "(max-min)/mean: a robust range-based scale-free "
            "illiquidity dispersion -- complementary to CoV which "
            "uses standard deviation."
        ),
        "original": "-(max-min)/mean(milliq,60)",
        "expression": (
            f"-1 * (ts_max({MILLIQ}, 60) - ts_min({MILLIQ}, 60)) "
            f"/ ts_mean({MILLIQ}, 60)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D13_05",
        "category": "milliq-vol-weighted-mean",
        "idea": (
            "Volume-weighted illiquidity mean -- ties obscure field "
            "to traded share volume. Structurally distinct from CoV "
            "and from Family C (which used returns, not milliq)."
        ),
        "original": "-mean(milliq*vol,60)/mean(vol,60)",
        "expression": (
            f"-1 * ts_mean({MILLIQ} * volume, 60) / ts_mean(volume, 60)"
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
