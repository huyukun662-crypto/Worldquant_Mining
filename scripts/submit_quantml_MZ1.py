"""QuantML round MZ1: novel mdl77 structures, no close/open allowed.

5 structurally distinct shapes never tried on mdl77 before:

  MZ1_01  Vol-of-vol (second-order): CoV(CoV(milliq, 20), 60)
  MZ1_02  Short/long MAC ratio: MAC(milliq, 30) / MAC(milliq, 250)
  MZ1_03  HL × milliq co-movement: ts_corr(high-low, milliq, 100)
  MZ1_04  Combined ratio CoV: CoV(milliq / bap20d, 100)
  MZ1_05  Milliq delta skewness: ts_skewness(ts_delta(milliq, 1), 100)

All wrapped in winsorize(., std=3) + trunc 0.10 INDUSTRY -- the
template that cleared FIX3_N/FIX4_K/FIX4_O. Negation per usual.
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


def mac(field: str, w: int = 100) -> str:
    return f"ts_mean(abs(ts_delta({field}, 1)), {w}) / ts_mean({field}, {w})"


def winz(expr: str, std: float = 3.0) -> str:
    return f"winsorize({expr}, std={std})"


SET_IND = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.10,
}


FACTORS: list[dict] = [
    {
        "id": "QM_MZ1_01",
        "category": "vol-of-vol",
        "idea": "Second-order CoV: variance of CoV(milliq,20) over 60d.",
        "original": "-winsorize(CoV(CoV(milliq,20), 60), 3)",
        "expression": winz(f"-1 * {cov_expr(cov(MILLIQ, 20), 60)}"),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_MZ1_02",
        "category": "short-long-MAC-ratio",
        "idea": "Term-structure of liquidity shocks: MAC30 / MAC250.",
        "original": "-winsorize(MAC(milliq,30)/MAC(milliq,250), 3)",
        "expression": winz(f"-1 * {mac(MILLIQ, 30)} / {mac(MILLIQ, 250)}"),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_MZ1_03",
        "category": "HL-milliq-corr",
        "idea": "Co-movement of daily range and illiquidity over 100d.",
        "original": "-ts_corr(high-low, milliq, 100)",
        "expression": f"-1 * ts_corr(high - low, {MILLIQ}, 100)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_MZ1_04",
        "category": "combined-ratio-CoV",
        "idea": "CoV of combined illiquidity milliq/bap20d ratio.",
        "original": "-winsorize(CoV(milliq/bap20d, 100), 3)",
        "expression": winz(f"-1 * {cov_expr(f'{MILLIQ} / {BAP}', 100)}"),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_MZ1_05",
        "category": "milliq-delta-skew",
        "idea": "Skewness of milliq deltas captures asymmetric jumps.",
        "original": "-ts_skewness(ts_delta(milliq,1), 100)",
        "expression": f"-1 * ts_skewness(ts_delta({MILLIQ}, 1), 100)",
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
