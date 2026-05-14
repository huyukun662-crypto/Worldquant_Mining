"""QuantML round D7: tune illiq-volatility from SH=1.10 toward gate (1.5).

Best obscure-only factor so far is D5_03:
  -ts_std_dev(mdl77_liquidityriskfactor_milliq, 250)
  @ SUBINDUSTRY decay=4 trunc=0.05  -> SH=1.10 TO=0.02 FIT=1.05

Settings observations:
  D5_01 W250 INDUSTRY d=2 t=0.03   SH=1.00
  D5_03 W250 SUBINDUSTRY d=4 t=0.05 SH=1.10  (SUBIND helped)
  D6_01 W250 MARKET d=4 t=0.10      SH=0.92  (MARKET hurt)
  D6_02 W500 SUBINDUSTRY d=2 t=0.03 SH=0.97  (W500 hurt)

So: SUBINDUSTRY + W250 is the sweet spot. D7 grids decay/trunc/window
around it + tries coefficient-of-variation and zscored shapes.

  D7_01  W250 SUBIND decay=0  t=0.05    (no decay)
  D7_02  W250 SUBIND decay=8  t=0.08    (heavier decay, looser trunc)
  D7_03  W150 SUBIND decay=4  t=0.05    (shorter window)
  D7_04  coefficient-of-variation: Std(illiq,250)/Mean(illiq,250)
  D7_05  W250 SUBIND decay=4  t=0.03    (tighter trunc)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"

FACTORS: list[dict] = [
    {
        "id": "QM_D7_01",
        "category": "illiq-vol-SUB-d0",
        "idea": "illiq-vol W250 SUBIND, no decay. Decay may be smearing signal.",
        "original": "-Std(milliq, 250)",
        "expression": f"-1 * ts_std_dev({MILLIQ}, 250)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 0,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D7_02",
        "category": "illiq-vol-SUB-d8-t08",
        "idea": "illiq-vol W250 SUBIND decay=8 t=0.08. Heavier smoothing + looser trunc.",
        "original": "-Std(milliq, 250)",
        "expression": f"-1 * ts_std_dev({MILLIQ}, 250)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_D7_03",
        "category": "illiq-vol-SUB-W150",
        "idea": "illiq-vol W150 SUBIND decay=4. Shorter window -- more responsive.",
        "original": "-Std(milliq, 150)",
        "expression": f"-1 * ts_std_dev({MILLIQ}, 150)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D7_04",
        "category": "illiq-coeff-of-variation",
        "idea": (
            "Coefficient of variation: Std(illiq,250)/Mean(illiq,250). "
            "Scale-free illiquidity instability -- normalises out the "
            "level so pure regime-instability remains. Sign negative."
        ),
        "original": "-Std(milliq,250)/Mean(milliq,250)",
        "expression": (
            f"-1 * ts_std_dev({MILLIQ}, 250) / ts_mean({MILLIQ}, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D7_05",
        "category": "illiq-vol-SUB-t03",
        "idea": "illiq-vol W250 SUBIND decay=4 t=0.03. Tighter trunc -- concentration.",
        "original": "-Std(milliq, 250)",
        "expression": f"-1 * ts_std_dev({MILLIQ}, 250)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.03,
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
