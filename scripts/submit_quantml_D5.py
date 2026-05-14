"""QuantML round D5: D4 sign-flip + W500 winning recipe push.

D4 produced 3 strong inverse signals on obscure model fields:
  D4_01 ts_std_dev(illiq, 250)    SH=-1.00  -- best to date
  D4_05 ts_mean(earnings_quality) SH=-0.88
  D4_04 ts_mean(earnings_expect)  SH=-0.66

D5 lineup: sign-flip the 3 winners + push D4_01 across grid using the
PV-winning recipe (W500, decay=2, trunc=0.02-0.03):

  D5_01  -ts_std_dev(illiq, 250) decay=2 INDUSTRY t=0.03  (raw flip)
  D5_02  -ts_std_dev(illiq, 500) decay=2 INDUSTRY t=0.02  (W500 recipe)
  D5_03  -ts_std_dev(illiq, 250) decay=4 SUBINDUSTRY t=0.05
  D5_04  -ts_mean(earnings_quality, 60) decay=4 IND t=0.05
  D5_05  -ts_mean(earnings_expect, 250) decay=2 IND t=0.03  (longer)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_D5_01",
        "category": "illiq-vol-FLIP-W250",
        "idea": (
            "D4_01 sign-flipped: -ts_std_dev(illiq, 250). "
            "Sign positive = long stable-illiquidity names "
            "(low liquidity-regime instability)."
        ),
        "original": "-Std(milliq, 250)",
        "expression": (
            "-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 2,
            "neutralization": "INDUSTRY",
            "truncation": 0.03,
        },
    },
    {
        "id": "QM_D5_02",
        "category": "illiq-vol-FLIP-W500",
        "idea": (
            "D4_01 flipped + W500 + tight trunc. The PV-winning recipe "
            "lifted body-asym-var from SH=1.51 to 1.94, hope same on "
            "illiq-vol."
        ),
        "original": "-Std(milliq, 500)",
        "expression": (
            "-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 500)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 2,
            "neutralization": "INDUSTRY",
            "truncation": 0.02,
        },
    },
    {
        "id": "QM_D5_03",
        "category": "illiq-vol-FLIP-SUBIND",
        "idea": (
            "D4_01 flipped + SUBINDUSTRY neut + decay=4 + t=0.05. "
            "Tighter neut sometimes lifts factors with cross-industry "
            "dispersion."
        ),
        "original": "-Std(milliq, 250)",
        "expression": (
            "-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D5_04",
        "category": "earnings-quality-FLIP",
        "idea": (
            "D4_05 sign-flipped: -mdl77 earnings-quality module raw, "
            "smoothed 60d. Short high earnings-quality? That sounds "
            "backwards economically but data > intuition."
        ),
        "original": "-Mean(eqm, 60)",
        "expression": (
            "-1 * ts_mean("
            "mdl77_2valuemomemtummodel_earningsqualitymodule, 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D5_05",
        "category": "earnings-expect-FLIP-W250",
        "idea": (
            "D4_04 flipped + W250 + decay=2 + t=0.03. Try long-window "
            "recipe on earnings-expectation module."
        ),
        "original": "-Mean(eem, 250)",
        "expression": (
            "-1 * ts_mean("
            "mdl77_2valuemomemtummodel_earningsexpectationmodule, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 2,
            "neutralization": "INDUSTRY",
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
