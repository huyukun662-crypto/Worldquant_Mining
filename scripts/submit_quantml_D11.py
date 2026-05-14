"""QuantML round D11: CoV shape on parallel obscure liquidity-risk fields.

The illiq coefficient-of-variation factor
  -ts_std_dev(milliq, 100) / ts_mean(milliq, 100)  @ SUBINDUSTRY
is stuck at SH=1.48-1.49 on the milliq (Amihud) field and every
(window, decay, trunc, universe, pasteurization, transform) lever is
exhausted.

The mdl77 liquidity-risk dataset has ~55 other fields, many cov=1.0
and uc=1 (effectively undiscovered). D11 applies the proven CoV shape
to the most promising parallel ones -- if any clears SH>=1.5 standalone
we have a viable structurally-distinct factor.

  D11_01  CoV volto       volume turnover instability
  D11_02  CoV cvvolp20d   volume-vol/price-vol ratio instability
  D11_03  CoV sip         short-interest-to-price instability
  D11_04  CoV mktlev      market-leverage instability
  D11_05  CoV si_ratio    short-interest-ratio instability

All W100 decay=0 SUBINDUSTRY t=0.05 -- the D9_05 champion setting
(SH=1.49 on milliq).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


def cov(field: str, window: int = 100) -> str:
    return (
        f"-1 * ts_std_dev({field}, {window}) / "
        f"ts_mean({field}, {window})"
    )


SET = {
    "universe": "TOP3000", "decay": 0,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D11_01",
        "category": "volto-CoV",
        "idea": "CoV of volume turnover -- turnover-instability liquidity signal.",
        "original": "-CoV(volto,100)",
        "expression": cov("mdl77_liquidityriskfactor_volto"),
        "settings_override": SET,
    },
    {
        "id": "QM_D11_02",
        "category": "cvvolp20d-CoV",
        "idea": (
            "CoV of cvvolp20d (20d volume-vol / price-vol ratio). "
            "Instability of the vol-ratio itself."
        ),
        "original": "-CoV(cvvolp20d,100)",
        "expression": cov("mdl77_liquidityriskfactor_cvvolp20d"),
        "settings_override": SET,
    },
    {
        "id": "QM_D11_03",
        "category": "sip-CoV",
        "idea": "CoV of sip (short-interest to price) -- short-pressure instability.",
        "original": "-CoV(sip,100)",
        "expression": cov("mdl77_liquidityriskfactor_sip"),
        "settings_override": SET,
    },
    {
        "id": "QM_D11_04",
        "category": "mktlev-CoV",
        "idea": "CoV of market leverage -- leverage-regime instability.",
        "original": "-CoV(mktlev,100)",
        "expression": cov("mdl77_liquidityriskfactor_mktlev"),
        "settings_override": SET,
    },
    {
        "id": "QM_D11_05",
        "category": "si_ratio-CoV",
        "idea": "CoV of short-interest ratio -- short-interest instability.",
        "original": "-CoV(si_ratio,100)",
        "expression": cov("mdl77_liquidityriskfactor_si_ratio"),
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
