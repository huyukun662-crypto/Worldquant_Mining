"""QuantML FIX6: amplify big-cap weight via cap multiplier.

J/L/M sub-uni warning is structural -- mdl77 liquidity variance is
weak on big caps. Directly amplify big-cap contribution by multiplying
the signal by power(cap, 0.5). The sqrt-cap factor lifts TOP1000
contribution roughly proportional to sqrt(market_cap), boosting the
sub-universe Sharpe without rank-flattening the cross-section.

  FIX6_J  signal_J * power(cap, 0.5)  winsorize SUBIND
  FIX6_L  signal_L * power(cap, 0.5)  winsorize INDUSTRY
  FIX6_M  signal_M * power(cap, 0.5)  winsorize INDUSTRY
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
        "id": "QM_FIX6_J",
        "category": "MAC*CoV*CoV-capwt",
        "idea": "J body * sqrt(cap) to lift TOP1000 sub-universe Sharpe.",
        "original": "winsorize(-MAC*CoV*CoV(HL) * sqrt(cap), 3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ)} * {cov(BAP)} * "
            f"{cov_expr('high - low')} * power(cap, 0.5)"
        ),
        "settings_override": SET_SUB,
    },
    {
        "id": "QM_FIX6_L",
        "category": "4leg-capwt",
        "idea": "L 4-leg body * sqrt(cap).",
        "original": "winsorize(-MAC*MAC*CoVHL*CoVvol * sqrt(cap), 3)",
        "expression": winz(
            f"-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP)} * "
            f"{cov_expr('high - low')} * {cov('volume')} * power(cap, 0.5)"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX6_M",
        "category": "MACbap*CoVHL*CoVvol-capwt",
        "idea": "M 3-leg body * sqrt(cap).",
        "original": "winsorize(-MAC(bap)*CoVHL*CoVvol * sqrt(cap), 3)",
        "expression": winz(
            f"-1 * {mac_norm(BAP)} * {cov_expr('high - low')} * "
            f"{cov('volume')} * power(cap, 0.5)"
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
