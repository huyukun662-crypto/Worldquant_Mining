"""QuantML round D9: shorter-window illiq-CoV to break the SH>=1.5 gate.

D8 progression (illiq coefficient-of-variation, SUBINDUSTRY-neut):
  D8_01 CoV W150 d=4 t=0.05   SH=1.38 FIT=1.45
  D8_02 CoV W100 d=4 t=0.05   SH=1.48 FIT=1.56  <- 0.02 from gate

Window monotonically helps as it shortens (W250->W150->W100 lifts
SH 1.28 -> 1.38 -> 1.48). D9 goes shorter: W40/W60/W80, plus a
trunc/decay micro-grid around the W100 near-miss.

  D9_01  CoV W80  d=4 t=0.05
  D9_02  CoV W60  d=4 t=0.05
  D9_03  CoV W40  d=4 t=0.05
  D9_04  CoV W100 d=4 t=0.03   (tighter trunc on the near-miss)
  D9_05  CoV W100 d=0 t=0.05   (no decay on the near-miss)
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
        "id": "QM_D9_01",
        "category": "illiq-CoV-W80",
        "idea": "CoV W80 -- continue the short-window trend.",
        "original": "-Std/Mean(milliq, 80)",
        "expression": cov(80),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D9_02",
        "category": "illiq-CoV-W60",
        "idea": "CoV W60.",
        "original": "-Std/Mean(milliq, 60)",
        "expression": cov(60),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D9_03",
        "category": "illiq-CoV-W40",
        "idea": "CoV W40 -- short enough that noise may start to dominate.",
        "original": "-Std/Mean(milliq, 40)",
        "expression": cov(40),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D9_04",
        "category": "illiq-CoV-W100-t03",
        "idea": "CoV W100 tight trunc 0.03 -- micro-grid on the D8_02 near-miss.",
        "original": "-Std/Mean(milliq, 100)",
        "expression": cov(100),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.03,
        },
    },
    {
        "id": "QM_D9_05",
        "category": "illiq-CoV-W100-d0",
        "idea": "CoV W100 no decay -- micro-grid on the D8_02 near-miss.",
        "original": "-Std/Mean(milliq, 100)",
        "expression": cov(100),
        "settings_override": {
            "universe": "TOP3000", "decay": 0,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
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
