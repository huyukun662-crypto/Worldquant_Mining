"""QuantML FIX5: last pass on J/L/M.

J still has LOW_SUB_UNIVERSE_SHARPE. L/M still have BOTH warnings.
New levers:
  * neut=MARKET (single bucket) -- spreads exposure across all caps,
    typically lifts TOP1000 sub-universe Sharpe.
  * ts_decay_linear(., 20) on winsorized signal -- additional time
    smoothing reduces day-to-day weight concentration.

  FIX5_J  MAC*CoV*CoV         winsorize -> ts_decay_linear 20, MARKET
  FIX5_L  MAC*MAC*CoVHL*CoVvol winsorize -> ts_decay_linear 20, MARKET
  FIX5_M  MAC(bap)*CoVHL*CoVvol  winsorize -> ts_decay_linear 20, MARKET
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


def smooth(expr: str, std: float = 3.0, dwin: int = 20) -> str:
    return f"ts_decay_linear(winsorize({expr}, std={std}), {dwin})"


SET_MKT = {
    "universe": "TOP3000", "decay": 0,
    "neutralization": "MARKET", "truncation": 0.10,
}


FACTORS: list[dict] = [
    {
        "id": "QM_FIX5_J",
        "category": "MAC*CoV*CoV-smooth-MKT",
        "idea": "winsorize + ts_decay_linear 20 + MARKET neutralization.",
        "original": "decay(winsorize(-MAC*CoV*CoV(HL), 3), 20) @ MKT",
        "expression": smooth(
            f"-1 * {mac_norm(MILLIQ)} * {cov(BAP)} * {cov_expr('high - low')}"
        ),
        "settings_override": SET_MKT,
    },
    {
        "id": "QM_FIX5_L",
        "category": "4leg-smooth-MKT",
        "idea": "MAC*MAC*CoVHL*CoVvol smoothed + MARKET.",
        "original": "decay(winsorize(-4leg, 3), 20) @ MKT",
        "expression": smooth(
            f"-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP)} * "
            f"{cov_expr('high - low')} * {cov('volume')}"
        ),
        "settings_override": SET_MKT,
    },
    {
        "id": "QM_FIX5_M",
        "category": "MACbap*CoVHL*CoVvol-smooth-MKT",
        "idea": "MAC(bap)*CoVHL*CoVvol smoothed + MARKET.",
        "original": "decay(winsorize(-3leg, 3), 20) @ MKT",
        "expression": smooth(
            f"-1 * {mac_norm(BAP)} * {cov_expr('high - low')} * {cov('volume')}"
        ),
        "settings_override": SET_MKT,
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
