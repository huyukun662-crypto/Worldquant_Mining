"""QuantML round D8: push illiq coefficient-of-variation toward SH>=1.5.

D7 progression on the illiq-volatility family:
  D7_01 vol W250 SUBIND d=0          SH=1.11
  D7_02 vol W250 SUBIND d=8 t=0.08   SH=1.08
  D7_03 vol W150 SUBIND d=4          SH=1.18  (shorter window helps)
  D7_04 CoV  W250 SUBIND d=4         SH=1.28 FIT=1.35  (CoV shape helps)

Two independent levers found: (a) shorter window, (b) coefficient-of-
variation shape Std/Mean. D8 combines them + grids around the combo.

  D8_01  CoV W150 SUBIND d=4 t=0.05   (CoV + short window)
  D8_02  CoV W100 SUBIND d=4 t=0.05   (even shorter)
  D8_03  CoV W150 SUBIND d=0 t=0.05   (no decay)
  D8_04  CoV W150 SUBIND d=4 t=0.03   (tight trunc)
  D8_05  CoV W150 SUBIND d=4 t=0.08   (loose trunc)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"


def cov(window: int) -> str:
    return (
        f"-1 * ts_std_dev({MILLIQ}, {window}) / "
        f"ts_mean({MILLIQ}, {window})"
    )


FACTORS: list[dict] = [
    {
        "id": "QM_D8_01",
        "category": "illiq-CoV-W150",
        "idea": "CoV + W150: combine the two D7 levers (CoV shape + short window).",
        "original": "-Std/Mean(milliq, 150)",
        "expression": cov(150),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D8_02",
        "category": "illiq-CoV-W100",
        "idea": "CoV + W100: even shorter window -- test if the trend continues.",
        "original": "-Std/Mean(milliq, 100)",
        "expression": cov(100),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D8_03",
        "category": "illiq-CoV-W150-d0",
        "idea": "CoV W150 no decay.",
        "original": "-Std/Mean(milliq, 150)",
        "expression": cov(150),
        "settings_override": {
            "universe": "TOP3000", "decay": 0,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D8_04",
        "category": "illiq-CoV-W150-t03",
        "idea": "CoV W150 tight trunc 0.03.",
        "original": "-Std/Mean(milliq, 150)",
        "expression": cov(150),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.03,
        },
    },
    {
        "id": "QM_D8_05",
        "category": "illiq-CoV-W150-t08",
        "idea": "CoV W150 loose trunc 0.08.",
        "original": "-Std/Mean(milliq, 150)",
        "expression": cov(150),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.08,
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
