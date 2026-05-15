"""QuantML round D20: extend mean_abs_change (D19_02 SH=1.13) into Family E/F.

D19_02 found mean_abs_change(milliq, 100) = SH=1.13 -- a new shape
distinct from variance/CoV. Apply the two proven amplification
structures (blend product + trade_when wrap) to test whether the
shape composes the same way:

  D20_01  Family E pattern: blend
          mean_abs_change(milliq) * mean_abs_change(bap20d) @ W100
          If multiplicative-blend is structural, this clears the gate.

  D20_02  Family F pattern: trade_when wrap
          trade_when(vol > avg120, -mean_abs_change(milliq,100), -1) d=0
          If trade_when conditional firing is structural, this clears.

  D20_03  mean_abs_change(milliq, 60)  shorter window
  D20_04  mean_abs_change(milliq, 250) longer window
  D20_05  -mean_abs_change(milliq,100) / mean(milliq,100)
          normalised mean_abs_change (CoV-like scale-free shape).

All @ SUBINDUSTRY decay=4 trunc=0.05 (D20_02 has decay=0).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP20D = "mdl77_liquidityriskfactor_bap20d"


def mac(field: str, w: int = 100) -> str:
    return f"ts_mean(abs(ts_delta({field}, 1)), {w})"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D20_01",
        "category": "MAC-milliq-bap20d-blend",
        "idea": (
            "Family E pattern with mean_abs_change shape instead of CoV: "
            "MAC(milliq, 100) * MAC(bap20d, 100). Tests if the blend "
            "structure is shape-agnostic."
        ),
        "original": "-MAC(milliq)*MAC(bap20d)",
        "expression": f"-1 * {mac(MILLIQ)} * {mac(BAP20D)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D20_02",
        "category": "MAC-trade_when-wrap",
        "idea": (
            "Family F pattern with mean_abs_change: "
            "trade_when(vol > avg120, -MAC(milliq), -1) decay=0."
        ),
        "original": "trade_when(vol>avg, -MAC(milliq,100), -1) d=0",
        "expression": (
            f"trade_when(volume > ts_mean(volume, 120), -1 * {mac(MILLIQ)}, -1)"
        ),
        "settings_override": {**SET, "decay": 0},
    },
    {
        "id": "QM_D20_03",
        "category": "MAC-milliq-W60",
        "idea": "mean_abs_change(milliq, 60) -- shorter window.",
        "original": "-MAC(milliq, 60)",
        "expression": f"-1 * {mac(MILLIQ, 60)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D20_04",
        "category": "MAC-milliq-W250",
        "idea": "mean_abs_change(milliq, 250) -- longer window.",
        "original": "-MAC(milliq, 250)",
        "expression": f"-1 * {mac(MILLIQ, 250)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D20_05",
        "category": "MAC-milliq-normalised",
        "idea": (
            "Normalised mean_abs_change (analog of CoV): "
            "-MAC(milliq,100) / mean(milliq,100). Scale-free version."
        ),
        "original": "-MAC(milliq)/mean(milliq)",
        "expression": f"-1 * {mac(MILLIQ)} / ts_mean({MILLIQ}, 100)",
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
