"""QuantML FIX3: wrap with winsorize(., std=3) + truncation 0.15.

Trunc 0.10 alone was insufficient. winsorize compresses
cross-sectional outliers BEFORE WQ's weight-assignment step, which is
the direct cause of CONCENTRATED_WEIGHT. Combined with looser
truncation 0.15 + INDUSTRY neutralization, this targets both
remaining warnings.

  FIX3_J  3-CoV          winsorize(., std=3) trunc 0.15 SUBIND decay 4
  FIX3_K  2-CoV W=150    winsorize(., std=3) trunc 0.15 SUBIND decay 4
  FIX3_L  4-CoV          winsorize(., std=3) trunc 0.15 INDUSTRY decay 4
  FIX3_M  3-CoV no milliq winsorize(., std=3) trunc 0.15 INDUSTRY decay 4
  FIX3_N  MAC_norm       winsorize(., std=3) trunc 0.15 INDUSTRY decay 4
  FIX3_O  Amihud         winsorize(., std=3) trunc 0.15 INDUSTRY decay 4
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
    "neutralization": "SUBINDUSTRY", "truncation": 0.15,
}
SET_IND = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.15,
}


FACTORS: list[dict] = [
    {
        "id": "QM_FIX3_J",
        "category": "3CoV-winz-t15",
        "idea": "Champion 3-CoV winsorized + trunc 0.15.",
        "original": "winsorize(-3CoV, std=3)",
        "expression": winz(
            f"-1 * {cov(MILLIQ)} * {cov(BAP)} * {cov_expr('high - low')}"
        ),
        "settings_override": SET_SUB,
    },
    {
        "id": "QM_FIX3_K",
        "category": "2CoV150-winz-t15",
        "idea": "milliq*bap20d W150 winsorized + trunc 0.15.",
        "original": "winsorize(-CoV*CoV150, std=3)",
        "expression": winz(f"-1 * {cov(MILLIQ, 150)} * {cov(BAP, 150)}"),
        "settings_override": SET_SUB,
    },
    {
        "id": "QM_FIX3_L",
        "category": "4CoV-winz-t15",
        "idea": "4-CoV winsorized + trunc 0.15 INDUSTRY.",
        "original": "winsorize(-4CoV, std=3)",
        "expression": winz(
            f"-1 * {cov(MILLIQ)} * {cov(BAP)} * "
            f"{cov_expr('high - low')} * {cov('volume')}"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX3_M",
        "category": "3CoV-noMilliq-winz-t15",
        "idea": "bap*HL*vol CoV winsorized + trunc 0.15 INDUSTRY.",
        "original": "winsorize(-3CoVnomilliq, std=3)",
        "expression": winz(
            f"-1 * {cov(BAP)} * {cov_expr('high - low')} * {cov('volume')}"
        ),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX3_N",
        "category": "MAC-winz-t15",
        "idea": "MAC_norm winsorized + trunc 0.15 INDUSTRY.",
        "original": "winsorize(-MAC*MAC, std=3)",
        "expression": winz(f"-1 * {mac_norm(MILLIQ)} * {mac_norm(BAP)}"),
        "settings_override": SET_IND,
    },
    {
        "id": "QM_FIX3_O",
        "category": "Amihud-winz-t15",
        "idea": "Amihud W=250 winsorized + trunc 0.15 INDUSTRY.",
        "original": "winsorize(-Amihud, std=3)",
        "expression": winz(
            "-1 * ts_mean(returns * volume, 250) / ts_mean(volume, 250)"
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
