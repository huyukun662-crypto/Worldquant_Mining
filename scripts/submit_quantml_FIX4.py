"""QuantML FIX4: structural rewrites for the 5 remaining warns.

FIX3_N proved that MAC_norm products + winsorize std=3 + trunc 0.15
+ INDUSTRY clears BOTH checks. Apply the same template to the 4
sub-universe-warning alphas by replacing CoV legs with MAC_norm legs
(smoother numerator, less concentration in mid-cap variance spikes).
For FIX3_O (Amihud, still has CONCENTRATED_WEIGHT), tighten winsorize
to std=2.

  FIX4_J  -MAC_norm(milliq) * CoV(bap20d) * CoV(HL)  winsorize std=3
  FIX4_K  -MAC_norm(milliq,150) * MAC_norm(bap20d,150)  winsorize std=3
  FIX4_L  -MAC_norm(milliq) * MAC_norm(bap20d) * CoV(HL) * CoV(vol)
  FIX4_M  -MAC_norm(bap20d) * CoV(HL) * CoV(vol)
  FIX4_O  Amihud winsorize std=2 (tighter) + trunc 0.10
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP = "mdl77_liquidityriskfactor_bap20d"


def cov(field: str, w: int = 100) -> str:
    return f"ts_std_dev({field}, {w}) / ts_mean({field}, {w})"


def cov_expr(expr: str, w: int = 100) -> str:
    return f"ts_std_dev({expr}, {w}) / ts_mean({expr}, {w})"


def mac_norm(field: str, w: int = 100) -> str:
    return f"ts_mean(abs(ts_delta({field}, 1)), {w}) / ts_mean({field}, {w})"


def winz(expr: str, std: float = 3.0) -> str:
    return f"winsorize({expr}, std={std})"


SET_IND = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.15,
}
SET_IND_T10 = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.10,
}


FACTORS: list[dict] = [
    {
        "id": "QM_FIX4_J",
        "category": "MAC*CoV*CoV-winz",
        "idea": "Replace 1st CoV leg with MAC_norm to smooth tail; rest unchanged.",
        "original": "winsorize(-MAC(milliq)*CoV(bap)*CoV(HL), std=3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ)} * {cov(BAP)} * {cov_expr('high - low')}"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX4_K",
        "category": "MAC*MAC150-winz",
        "idea": "Replace BOTH CoV legs of K with MAC_norm at W=150.",
        "original": "winsorize(-MAC(milliq,150)*MAC(bap,150), std=3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ, 150)} * {mac_norm(BAP, 150)}"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX4_L",
        "category": "MAC*MAC*CoVHL*CoVvol-winz",
        "idea": "4-leg: MAC for mdl77 pair, CoV for HL/vol PV pair.",
        "original": "winsorize(-MAC*MAC*CoV(HL)*CoV(vol), std=3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP)} * "
            f"{cov_expr('high - low')} * {cov('volume')}"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX4_M",
        "category": "MAC(bap)*CoVHL*CoVvol-winz",
        "idea": "3-leg without milliq: MAC(bap) * CoV(HL) * CoV(vol).",
        "original": "winsorize(-MAC(bap)*CoV(HL)*CoV(vol), std=3)",
        "expression": winz(
            f"-1 * {mac_norm(BAP)} * {cov_expr('high - low')} * {cov('volume')}"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX4_O",
        "category": "Amihud-winz-std2-t10",
        "idea": "Amihud W=250 with tighter winsorize std=2 + trunc 0.10.",
        "original": "winsorize(-Amihud, std=2)",
        "expression": winz(
            "-1 * ts_mean(returns * volume, 250) / ts_mean(volume, 250)",
            std=2.0,
        ),
        "settings_override": SET_IND_T10,
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
