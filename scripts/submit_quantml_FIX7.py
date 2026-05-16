"""QuantML FIX7: re-do FIX6 with unitless cap weighting.

FIX6 failed unit check: cap is Unit[CSPrice:1, CSShare:1] (dollars),
not allowed inside power(). Use rank(cap) which is unitless [0, 1],
then power(rank(cap), 0.5) gives concave big-cap weight in [0, 1].
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP = "mdl77_liquidityriskfactor_bap20d"

CAPWT = "power(rank(cap), 0.5)"


def cov(field: str, w: int = 100) -> str:
    return f"ts_std_dev({field}, {w}) / ts_mean({field}, {w})"


def cov_expr(expr: str, w: int = 100) -> str:
    return f"ts_std_dev({expr}, {w}) / ts_mean({expr}, {w})"


def mac_norm(field: str, w: int = 100) -> str:
    return f"ts_mean(abs(ts_delta({field}, 1)), {w}) / ts_mean({field}, {w})"


def winz(expr: str, std: float = 3.0) -> str:
    return f"winsorize({expr}, std={std})"


SET_SUB = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.10,
}
SET_IND = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.10,
}


FACTORS: list[dict] = [
    {
        "id": "QM_FIX7_J",
        "category": "MAC*CoV*CoV-rankcap",
        "idea": "J body * sqrt(rank(cap)) to lift TOP1000 weight.",
        "original": "winsorize(-MAC*CoV*CoV(HL) * sqrt(rank(cap)), 3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ)} * {cov(BAP)} * "
            f"{cov_expr('high - low')} * {CAPWT}"
        ),
        "settings_override": SET_SUB,
    },
    {
        "id": "QM_FIX7_L",
        "category": "4leg-rankcap",
        "idea": "L 4-leg body * sqrt(rank(cap)).",
        "original": "winsorize(-MAC*MAC*CoVHL*CoVvol * sqrt(rank(cap)), 3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP)} * "
            f"{cov_expr('high - low')} * {cov('volume')} * {CAPWT}"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX7_M",
        "category": "MACbap*CoVHL*CoVvol-rankcap",
        "idea": "M 3-leg body * sqrt(rank(cap)).",
        "original": "winsorize(-MAC(bap)*CoVHL*CoVvol * sqrt(rank(cap)), 3)",
        "expression": winz(
            f"-1 * {mac_norm(BAP)} * {cov_expr('high - low')} * "
            f"{cov('volume')} * {CAPWT}"
        ),
        "settings_override": SET_IND,
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
