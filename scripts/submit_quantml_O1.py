"""QuantML round O1: push OA30 (SH=1.85, TO=0.54) under gate SH>=1.75/TO<0.25.

OA30 is the highest-SH factor in 159 submissions but with TO=0.54
under default settings (decay=0 INDUSTRY trunc=0.08). Heavy decay
should compress TO; concern is SH drop.

Expression (from OpenAlpha port):
  -1 * ts_regression(ts_rank(close, 10), ts_rank(abs(returns), 10),
                     10, rettype=2)

Five setting points to grid-search the TO compression:

  O1_01  decay=16  INDUSTRY  trunc=0.08
  O1_02  decay=32  INDUSTRY  trunc=0.08
  O1_03  decay=16  SUBINDUSTRY  trunc=0.05
  O1_04  decay=16  MARKET  trunc=0.10
  O1_05  decay=8   INDUSTRY  trunc=0.05   (light decay + tight trunc)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

OA30 = (
    "-1 * ts_regression(ts_rank(close, 10), "
    "ts_rank(abs(returns), 10), 10, rettype=2)"
)


FACTORS: list[dict] = [
    {
        "id": "QM_O1_01",
        "category": "OA30-d16-IND",
        "idea": "OA30 with decay=16 INDUSTRY trunc=0.08. Standard heavy-decay TO compression.",
        "original": "OA30 setting variant",
        "expression": OA30,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 16,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_O1_02",
        "category": "OA30-d32-IND",
        "idea": "OA30 with decay=32 -- maximum smoothing.",
        "original": "OA30 setting variant",
        "expression": OA30,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 32,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_O1_03",
        "category": "OA30-d16-SUB-t05",
        "idea": "OA30 d=16 SUBINDUSTRY t=0.05 -- tighter neut + concentration.",
        "original": "OA30 setting variant",
        "expression": OA30,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 16,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_O1_04",
        "category": "OA30-d16-MKT-t10",
        "idea": "OA30 d=16 MARKET t=0.10 -- looser neut + diversification.",
        "original": "OA30 setting variant",
        "expression": OA30,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 16,
            "neutralization": "MARKET",
            "truncation": 0.10,
        },
    },
    {
        "id": "QM_O1_05",
        "category": "OA30-d8-IND-t05",
        "idea": "OA30 d=8 IND t=0.05 -- light decay + tight bets.",
        "original": "OA30 setting variant",
        "expression": OA30,
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
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
