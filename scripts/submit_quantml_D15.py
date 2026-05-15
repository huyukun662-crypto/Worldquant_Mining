"""QuantML round D15: 5 genuinely-different shape types on milliq + diverse pairs.

D13/D14 confirmed: only variance-class shapes carry signal, and CoV-blend
works best with SAME-CATEGORY field pairs. D15 tries 5 structurally
distinct shape ideas that don't repeat any prior shape:

  D15_01 ts_skewness(milliq, 100)
         Third moment -- asymmetric distribution of illiquidity.
         Structurally different from second moment (std/CoV).

  D15_02 -group_relative milliq, level + CoV
         (milliq - group_mean(milliq, subindustry)) / milliq
         How much more illiquid is this stock than peers?
         Group-relative SHAPE, not group-NEUTRALIZATION.

  D15_03 -ts_mean(milliq,100) * ts_std_dev(milliq,100)
         Level x volatility interaction (single-field, not blend).
         Different from CoV (which is std/mean, not std*mean).

  D15_04 -CoV(milliq,100) * CoV(impduration,100)
         New Family E field pair: milliq x impduration (implied
         duration, uc=21). Test whether milliq pairs widely.

  D15_05 -CoV(milliq,100) * CoV(bap20d,100) * CoV(cvvolp20d,100)
         Triple product -- 3-way liquidity-instability interaction.
         If pairwise gives SH=1.89, does triple help or hurt?

All @ SUBINDUSTRY decay=4 trunc=0.05 (Family E sweet-spot).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP20D = "mdl77_liquidityriskfactor_bap20d"
CVVOLP = "mdl77_liquidityriskfactor_cvvolp20d"
IMPDUR = "mdl77_liquidityriskfactor_impduration"


def cov(field: str, w: int = 100) -> str:
    return f"ts_std_dev({field}, {w}) / ts_mean({field}, {w})"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D15_01",
        "category": "milliq-skewness",
        "idea": "Third moment of illiquidity -- distribution asymmetry.",
        "original": "-ts_skewness(milliq,100)",
        "expression": f"-1 * ts_skewness({MILLIQ}, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D15_02",
        "category": "milliq-group-relative-CoV",
        "idea": (
            "CoV of group-relative illiquidity ratio. Captures "
            "instability of peer-relative liquidity rank."
        ),
        "original": "-CoV((milliq-grp_mean)/milliq,100)",
        "expression": (
            f"-1 * ts_std_dev(({MILLIQ} - group_mean({MILLIQ}, 1, subindustry)) "
            f"/ {MILLIQ}, 100) "
            f"/ ts_mean(({MILLIQ} - group_mean({MILLIQ}, 1, subindustry)) "
            f"/ {MILLIQ}, 100)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D15_03",
        "category": "milliq-mean-x-std",
        "idea": (
            "Level x volatility product (single-field). Different from "
            "CoV which is std/mean -- this is std*mean."
        ),
        "original": "-mean*std(milliq,100)",
        "expression": f"-1 * ts_mean({MILLIQ}, 100) * ts_std_dev({MILLIQ}, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D15_04",
        "category": "illiq-impduration-blend",
        "idea": "New Family E pair: milliq x impduration (implied duration).",
        "original": "-CoV(milliq)*CoV(impduration)",
        "expression": f"-1 * {cov(MILLIQ)} * {cov(IMPDUR)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D15_05",
        "category": "illiq-triple-product",
        "idea": (
            "3-way liquidity-instability product: milliq * bap20d * "
            "cvvolp20d. Tests whether interaction is monotone in arity."
        ),
        "original": "-CoV(milliq)*CoV(bap20d)*CoV(cvvolp20d)",
        "expression": (
            f"-1 * {cov(MILLIQ)} * {cov(BAP20D)} * {cov(CVVOLP)}"
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
