"""QuantML round D21: push MAC-blend toward the SH>=1.5 gate.

D19/D20 found MAC (mean_abs_change) is a new tsfresh-style shape that
carries signal on milliq. Best so far:
  D20_01  MAC(milliq,100) * MAC(bap20d,100)         SH=1.43
  D20_05  MAC(milliq,100) / mean(milliq,100)        SH=1.34  (scale-free)

D21 tunes the MAC-blend to clear the gate -- mirroring the CoV
champion D12_05 path (W150 + decay tuning + scale-free) and one
cross-shape mix:

  D21_01  Normalised MAC blend:
          (MAC/mean)(milliq) * (MAC/mean)(bap20d)
          Scale-free MAC blend.

  D21_02  MAC blend @ W150 (CoV champion window):
          MAC(milliq,150) * MAC(bap20d,150)

  D21_03  MAC blend @ decay=0:
          MAC(milliq,100) * MAC(bap20d,100) @ decay=0

  D21_04  Cross-shape blend:
          MAC(milliq,100) * CoV(bap20d,100)

  D21_05  Triple MAC blend:
          MAC(milliq) * MAC(bap20d) * MAC(cvvolp20d)

All @ SUBINDUSTRY decay=4 trunc=0.05 (D21_03 has decay=0).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP20D = "mdl77_liquidityriskfactor_bap20d"
CVVOLP = "mdl77_liquidityriskfactor_cvvolp20d"


def mac(field: str, w: int = 100) -> str:
    return f"ts_mean(abs(ts_delta({field}, 1)), {w})"


def mac_norm(field: str, w: int = 100) -> str:
    return f"{mac(field, w)} / ts_mean({field}, {w})"


def cov(field: str, w: int = 100) -> str:
    return f"ts_std_dev({field}, {w}) / ts_mean({field}, {w})"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D21_01",
        "category": "MAC_norm-blend",
        "idea": "Scale-free MAC blend: (MAC/mean)(milliq) * (MAC/mean)(bap20d).",
        "original": "-MAC_norm(milliq)*MAC_norm(bap20d)",
        "expression": f"-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP20D)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D21_02",
        "category": "MAC-blend-W150",
        "idea": "MAC blend at W150 (CoV champion window).",
        "original": "-MAC(milliq,150)*MAC(bap20d,150)",
        "expression": f"-1 * {mac(MILLIQ, 150)} * {mac(BAP20D, 150)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D21_03",
        "category": "MAC-blend-decay0",
        "idea": "MAC blend @ decay=0.",
        "original": "-MAC(milliq)*MAC(bap20d) d=0",
        "expression": f"-1 * {mac(MILLIQ)} * {mac(BAP20D)}",
        "settings_override": {**SET, "decay": 0},
    },
    {
        "id": "QM_D21_04",
        "category": "MAC-CoV-cross-blend",
        "idea": (
            "Cross-shape blend: MAC(milliq) * CoV(bap20d). Tests "
            "whether mixing shapes amplifies."
        ),
        "original": "-MAC(milliq)*CoV(bap20d)",
        "expression": f"-1 * {mac(MILLIQ)} * {cov(BAP20D)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D21_05",
        "category": "MAC-triple-blend",
        "idea": "Triple MAC: milliq * bap20d * cvvolp20d.",
        "original": "-MAC(milliq)*MAC(bap20d)*MAC(cvvolp20d)",
        "expression": (
            f"-1 * {mac(MILLIQ)} * {mac(BAP20D)} * {mac(CVVOLP)}"
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
