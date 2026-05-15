"""QuantML FIX1: rewrite the 6 alphas that simulated OK but failed
deliverability checks (CONCENTRATED_WEIGHT / LOW_SUB_UNIVERSE_SHARPE).

Strategy:
  * Wrap signal with rank()  -> flattens weights, kills CONCENTRATED_WEIGHT,
    typically also lifts sub-universe Sharpe since rank-IC propagates to
    TOP1000/TOP500.
  * Where signal is mdl77-only (no PV legs), bump truncation 0.05 -> 0.08
    as additional defense.

  FIX1_J  champion 3-CoV         (was N1nO1Pdg, LOW_SUB_UNIVERSE_SHARPE)
  FIX1_K  CoV milliq*bap20d W150 (was JjnYx5bO, LOW_SUB_UNIVERSE_SHARPE)
  FIX1_L  4-CoV product          (was RRNrjnxd, CONC+SUB)
  FIX1_M  3-CoV no milliq        (was 88OL5epm,  CONC+SUB)
  FIX1_N  MAC_norm double        (was WjN9G1YO,  CONC)
  FIX1_O  Amihud W=250           (was rKbvg611,  CONC)
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


SET_SUB = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.08,
}
SET_IND = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.08,
}


FACTORS: list[dict] = [
    {
        "id": "QM_FIX1_J",
        "category": "3CoV-rank-fix",
        "idea": "Champion 3-CoV wrapped in rank to clear LOW_SUB_UNIVERSE_SHARPE.",
        "original": "rank(-CoV(milliq)*CoV(bap20d)*CoV(HL))",
        "expression": (
            f"rank(-1 * {cov(MILLIQ)} * {cov(BAP)} * {cov_expr('high - low')})"
        ),
        "settings_override": SET_SUB,
    },
    {
        "id": "QM_FIX1_K",
        "category": "milliq-bap-rank-fix",
        "idea": "milliq*bap20d W150 wrapped in rank.",
        "original": "rank(-CoV(milliq,150)*CoV(bap20d,150))",
        "expression": (
            f"rank(-1 * {cov(MILLIQ, 150)} * {cov(BAP, 150)})"
        ),
        "settings_override": SET_SUB,
    },
    {
        "id": "QM_FIX1_L",
        "category": "4CoV-rank-fix",
        "idea": "4-CoV wrapped in rank + trunc 0.08 INDUSTRY.",
        "original": "rank(-CoV(milliq)*CoV(bap20d)*CoV(HL)*CoV(vol))",
        "expression": (
            f"rank(-1 * {cov(MILLIQ)} * {cov(BAP)} * "
            f"{cov_expr('high - low')} * {cov('volume')})"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX1_M",
        "category": "3CoV-noMilliq-rank-fix",
        "idea": "bap*HL*volume CoV wrapped in rank + INDUSTRY.",
        "original": "rank(-CoV(bap20d)*CoV(HL)*CoV(vol))",
        "expression": (
            f"rank(-1 * {cov(BAP)} * {cov_expr('high - low')} * {cov('volume')})"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX1_N",
        "category": "MAC-norm-rank-fix",
        "idea": "MAC_norm double-leg wrapped in rank + INDUSTRY.",
        "original": "rank(-MAC_norm(milliq)*MAC_norm(bap20d))",
        "expression": (
            f"rank(-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP)})"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX1_O",
        "category": "Amihud-rank-fix",
        "idea": "Amihud W=250 wrapped in rank + INDUSTRY.",
        "original": "rank(-mean(returns*volume,250)/mean(volume,250))",
        "expression": (
            "rank(-1 * ts_mean(returns * volume, 250) / ts_mean(volume, 250))"
        ),
        "settings_override": {**SET_IND, "decay": 2},
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
