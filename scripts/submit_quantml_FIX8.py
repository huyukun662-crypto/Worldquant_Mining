"""QuantML FIX8: cube rank(cap) for aggressive big-cap concentration.

FIX7 sqrt(rank(cap)) lifted SH 1.7->1.86/2.26/1.80 but sub-uni still
warned. Cube power concentrates weight heavily on TOP1000 names which
dominates TOP1000 sub-universe Sharpe directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"
BAP = "mdl77_liquidityriskfactor_bap20d"

CAPWT = "power(rank(cap), 3)"


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
        "id": "QM_FIX8_J",
        "category": "MAC*CoV*CoV-cubecap",
        "idea": "J body * rank(cap)^3.",
        "original": "winsorize(-MAC*CoV*CoV(HL) * rank(cap)^3, 3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ)} * {cov(BAP)} * "
            f"{cov_expr('high - low')} * {CAPWT}"
        ),
        "settings_override": SET_SUB,
    },
    {
        "id": "QM_FIX8_L",
        "category": "4leg-cubecap",
        "idea": "L 4-leg body * rank(cap)^3.",
        "original": "winsorize(-4leg * rank(cap)^3, 3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP)} * "
            f"{cov_expr('high - low')} * {cov('volume')} * {CAPWT}"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX8_M",
        "category": "MACbap*CoVHL*CoVvol-cubecap",
        "idea": "M 3-leg body * rank(cap)^3.",
        "original": "winsorize(-3leg * rank(cap)^3, 3)",
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
