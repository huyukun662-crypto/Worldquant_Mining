"""QuantML round D10: new levers for illiq-CoV stuck at SH=1.48.

D9 confirmed a hard plateau: illiq coefficient-of-variation
  -ts_std_dev(milliq, W) / ts_mean(milliq, W)  @ SUBINDUSTRY
sits at SH=1.48 for every W in {60, 80, 100, 150} and is insensitive
to decay and truncation. Window/decay/trunc levers are exhausted.

D10 tries levers OUTSIDE the (window, decay, trunc) box:

  D10_01  rank-transformed CoV          rank(CoV)        SUBIND
  D10_02  zscore-transformed CoV        zscore(CoV)      SUBIND
  D10_03  CoV W100 on TOP1000 universe  (universe lever)
  D10_04  CoV W100 pasteurization OFF   (pasteurization lever)
  D10_05  illiq-CoV x bap20d-CoV blend  two parallel liquidity-
            instability sources, multiplied (interaction, not sum --
            avoids the additive-composite dilution seen before)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP20D = "mdl77_liquidityriskfactor_bap20d"


def cov(field: str, window: int) -> str:
    return f"ts_std_dev({field}, {window}) / ts_mean({field}, {window})"


FACTORS: list[dict] = [
    {
        "id": "QM_D10_01",
        "category": "illiq-CoV-ranked",
        "idea": (
            "rank() the CoV cross-sectionally before neutralisation. "
            "Rank transform compresses tails -- may stabilise the "
            "signal past the 1.48 plateau."
        ),
        "original": "-rank(CoV(milliq,100))",
        "expression": f"-1 * rank({cov(MILLIQ, 100)})",
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D10_02",
        "category": "illiq-CoV-zscored",
        "idea": "zscore() the CoV cross-sectionally before neutralisation.",
        "original": "-zscore(CoV(milliq,100))",
        "expression": f"-1 * zscore({cov(MILLIQ, 100)})",
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D10_03",
        "category": "illiq-CoV-TOP1000",
        "idea": (
            "CoV W100 on TOP1000 universe. Smaller universe hurt PV "
            "factors historically, but illiquidity signal may be "
            "stronger in the larger-cap subset."
        ),
        "original": "-CoV(milliq,100)",
        "expression": f"-1 * {cov(MILLIQ, 100)}",
        "settings_override": {
            "universe": "TOP1000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
        },
    },
    {
        "id": "QM_D10_04",
        "category": "illiq-CoV-pasteur-OFF",
        "idea": "CoV W100 with pasteurization OFF -- different point treatment.",
        "original": "-CoV(milliq,100)",
        "expression": f"-1 * {cov(MILLIQ, 100)}",
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
            "neutralization": "SUBINDUSTRY", "truncation": 0.05,
            "pasteurization": "OFF",
        },
    },
    {
        "id": "QM_D10_05",
        "category": "illiq-bap20d-CoV-blend",
        "idea": (
            "Multiplicative blend of two parallel liquidity-instability "
            "CoVs: milliq-CoV * bap20d-CoV. Interaction (not sum) so it "
            "avoids the additive-composite dilution. Both are obscure "
            "liquidity-risk fields; their product fires only when both "
            "agree."
        ),
        "original": "-CoV(milliq,100) * CoV(bap20d,100)",
        "expression": (
            f"-1 * {cov(MILLIQ, 100)} * {cov(BAP20D, 100)}"
        ),
        "settings_override": {
            "universe": "TOP3000", "decay": 4,
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
