"""QuantML round D12: extend the D10_05 multiplicative-CoV-blend win.

D10_05 was the breakthrough: the product of two coefficient-of-variation
signals on parallel obscure liquidity-risk fields
  -1 * CoV(milliq,100) * CoV(bap20d,100)  @ SUBINDUSTRY decay=4 t=0.05
cleared the gate at SH=1.80 TO=0.048 FIT=2.67 (alpha 88O7Q76V).

Single-field CoVs are weak (volto 0.24, cvvolp20d 0.43, sip 0.51) but
the milliq*bap20d *interaction* is strong. D12 probes whether the
interaction effect generalises to other liquidity-field pairs, and
tunes the winning blend.

  D12_01  CoV(milliq) * CoV(volto)     Amihud x turnover
  D12_02  CoV(milliq) * CoV(cvvolp20d) Amihud x vol-ratio
  D12_03  CoV(bap20d) * CoV(volto)     spread x turnover
  D12_04  D10_05 winner @ decay=0      tune the champion
  D12_05  D10_05 winner @ W150         tune the champion
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP20D = "mdl77_liquidityriskfactor_bap20d"
VOLTO = "mdl77_liquidityriskfactor_volto"
CVVOLP = "mdl77_liquidityriskfactor_cvvolp20d"


def cov(field: str, w: int = 100) -> str:
    return f"ts_std_dev({field}, {w}) / ts_mean({field}, {w})"


def blend(f1: str, f2: str, w: int = 100) -> str:
    return f"-1 * {cov(f1, w)} * {cov(f2, w)}"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D12_01",
        "category": "milliq-volto-CoV-blend",
        "idea": "CoV(milliq) * CoV(volto): Amihud illiq instability x turnover instability.",
        "original": "-CoV(milliq)*CoV(volto)",
        "expression": blend(MILLIQ, VOLTO),
        "settings_override": SET,
    },
    {
        "id": "QM_D12_02",
        "category": "milliq-cvvolp-CoV-blend",
        "idea": "CoV(milliq) * CoV(cvvolp20d): Amihud x volume-vol-ratio instability.",
        "original": "-CoV(milliq)*CoV(cvvolp20d)",
        "expression": blend(MILLIQ, CVVOLP),
        "settings_override": SET,
    },
    {
        "id": "QM_D12_03",
        "category": "bap20d-volto-CoV-blend",
        "idea": "CoV(bap20d) * CoV(volto): spread instability x turnover instability.",
        "original": "-CoV(bap20d)*CoV(volto)",
        "expression": blend(BAP20D, VOLTO),
        "settings_override": SET,
    },
    {
        "id": "QM_D12_04",
        "category": "D10_05-champion-d0",
        "idea": "D10_05 winner (milliq*bap20d blend) tuned to decay=0.",
        "original": "-CoV(milliq)*CoV(bap20d) d=0",
        "expression": blend(MILLIQ, BAP20D),
        "settings_override": {**SET, "decay": 0},
    },
    {
        "id": "QM_D12_05",
        "category": "D10_05-champion-W150",
        "idea": "D10_05 winner tuned to W150 windows.",
        "original": "-CoV(milliq)*CoV(bap20d) W150",
        "expression": blend(MILLIQ, BAP20D, 150),
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
