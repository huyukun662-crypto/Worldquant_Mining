"""QuantML round D22: more tsfresh shapes -- MAD, RMS, abs_energy, third-moment.

D19/D21 validated tsfresh shape extraction: mean_abs_change gives a new
shape that blends to SH=1.83. D22 continues the tsfresh-style operator
sweep with 5 more shapes accessible in FASTEXPR:

  D22_01 MAD blend          median absolute deviation
         MAD(x,W) = mean(|x - mean(x,W)|, W)  -- anchored to mean,
         distinct from MAC which is anchored to lag-1.
         Blend pattern: -MAD(milliq) * MAD(bap20d).

  D22_02 RMS-of-changes     root-mean-square of daily changes
         RMS_dx = (mean(delta(x,1)^2, W))^0.5
         Blend: -RMS_dx(milliq) * RMS_dx(bap20d).

  D22_03 abs_energy ratio   normalised L2 energy
         -sum(x^2, W) / sum(x, W)^2  -- scale-invariant energy.

  D22_04 third-moment delta time_reversal_asymmetry analogue
         -mean(delta(x,1)^3, W)  -- third power of changes.
         Captures asymmetry of change distribution.

  D22_05 MAD normalised CoV-of-MAD analogue
         -MAD(x,W) / mean(x,W)  on milliq -- scale-free MAD.

All @ SUBINDUSTRY decay=4 trunc=0.05.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP20D = "mdl77_liquidityriskfactor_bap20d"


def mad(field: str, w: int = 100) -> str:
    return f"ts_mean(abs({field} - ts_mean({field}, {w})), {w})"


def rms_dx(field: str, w: int = 100) -> str:
    return f"power(ts_mean(power(ts_delta({field}, 1), 2), {w}), 0.5)"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D22_01",
        "category": "MAD-blend",
        "idea": "MAD blend: -MAD(milliq,100) * MAD(bap20d,100).",
        "original": "-MAD(milliq)*MAD(bap20d)",
        "expression": f"-1 * {mad(MILLIQ)} * {mad(BAP20D)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D22_02",
        "category": "RMS-dx-blend",
        "idea": "RMS-of-changes blend.",
        "original": "-RMS_dx(milliq)*RMS_dx(bap20d)",
        "expression": f"-1 * {rms_dx(MILLIQ)} * {rms_dx(BAP20D)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D22_03",
        "category": "abs_energy-ratio",
        "idea": "Scale-invariant L2 energy: -sum(x^2)/sum(x)^2.",
        "original": "-sum(x^2)/sum(x)^2 milliq",
        "expression": (
            f"-1 * ts_sum(power({MILLIQ}, 2), 100) "
            f"/ power(ts_sum({MILLIQ}, 100), 2)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D22_04",
        "category": "third-moment-delta",
        "idea": "Time-reversal-asymmetry analogue: -mean(delta(x,1)^3, 100).",
        "original": "-mean(delta(milliq,1)^3, 100)",
        "expression": (
            f"-1 * ts_mean(power(ts_delta({MILLIQ}, 1), 3), 100)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D22_05",
        "category": "MAD-normalised",
        "idea": "Scale-free MAD on milliq: -MAD(milliq,100)/mean(milliq,100).",
        "original": "-MAD(milliq)/mean(milliq)",
        "expression": f"-1 * {mad(MILLIQ)} / ts_mean({MILLIQ}, 100)",
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
