"""QuantML FIX2: revert rank() approach (it crushed Sharpe 1.9 -> 0.7).

New strategy: keep the original expression intact (preserve magnitude),
but loosen truncation 0.05 -> 0.10 and broaden neutralization
SUBINDUSTRY -> INDUSTRY where concentration is the problem. For sub-
universe Sharpe, also bump decay to smooth tail weights.

  FIX2_J  champion 3-CoV          trunc 0.10 SUBIND decay 8
  FIX2_K  CoV milliq*bap20d W150  trunc 0.10 SUBIND decay 8
  FIX2_L  4-CoV product           trunc 0.10 INDUSTRY decay 4
  FIX2_M  3-CoV no milliq         trunc 0.10 INDUSTRY decay 4
  FIX2_N  MAC_norm double         trunc 0.10 INDUSTRY decay 4
  FIX2_O  Amihud W=250            trunc 0.10 INDUSTRY decay 4
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


SET_SUB_T10_D8 = {
    "universe": "TOP3000", "decay": 8,
    "neutralization": "SUBINDUSTRY", "truncation": 0.10,
}
SET_IND_T10 = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.10,
}


FACTORS: list[dict] = [
    {
        "id": "QM_FIX2_J",
        "category": "3CoV-trunc10-decay8",
        "idea": "champion 3-CoV with trunc 0.10 + decay 8 to spread weight.",
        "original": "-CoV(milliq)*CoV(bap20d)*CoV(HL)",
        "expression": (
            f"-1 * {cov(MILLIQ)} * {cov(BAP)} * {cov_expr('high - low')}"
        ),
        "settings_override": SET_SUB_T10_D8,
    },
    {
        "id": "QM_FIX2_K",
        "category": "milliq-bap150-trunc10-decay8",
        "idea": "milliq*bap20d W150 with trunc 0.10 + decay 8.",
        "original": "-CoV(milliq,150)*CoV(bap20d,150)",
        "expression": f"-1 * {cov(MILLIQ, 150)} * {cov(BAP, 150)}",
        "settings_override": SET_SUB_T10_D8,
    },
    {
        "id": "QM_FIX2_L",
        "category": "4CoV-trunc10-IND",
        "idea": "4-CoV with trunc 0.10 + INDUSTRY to clear concentration.",
        "original": "-CoV(milliq)*CoV(bap20d)*CoV(HL)*CoV(vol)",
        "expression": (
            f"-1 * {cov(MILLIQ)} * {cov(BAP)} * "
            f"{cov_expr('high - low')} * {cov('volume')}"
        ),
        "settings_override": SET_IND_T10,
    },
    {
        "id": "QM_FIX2_M",
        "category": "3CoV-noMilliq-trunc10-IND",
        "idea": "bap*HL*volume CoV with trunc 0.10 + INDUSTRY.",
        "original": "-CoV(bap20d)*CoV(HL)*CoV(vol)",
        "expression": (
            f"-1 * {cov(BAP)} * {cov_expr('high - low')} * {cov('volume')}"
        ),
        "settings_override": SET_IND_T10,
    },
    {
        "id": "QM_FIX2_N",
        "category": "MAC-norm-trunc10-IND",
        "idea": "MAC_norm double-leg with trunc 0.10 + INDUSTRY.",
        "original": "-MAC_norm(milliq)*MAC_norm(bap20d)",
        "expression": f"-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP)}",
        "settings_override": SET_IND_T10,
    },
    {
        "id": "QM_FIX2_O",
        "category": "Amihud-trunc10-IND",
        "idea": "Amihud W=250 with trunc 0.10 + decay 4 + INDUSTRY.",
        "original": "-mean(returns*volume,250)/mean(volume,250)",
        "expression": (
            "-1 * ts_mean(returns * volume, 250) / ts_mean(volume, 250)"
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
