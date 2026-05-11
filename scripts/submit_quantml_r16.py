"""QuantML round 16: push R15_03 from SH=1.20 to SH>1.3.

R15_03 hit SH=1.20 with body-skew on INDUSTRY-neut, decay=4, trunc=0.05.
Closest non-viable yet -- gap of just 0.10 SH.

Five settings + window variations to grid-search:

  R16_01  body-skew d=8 t=0.05      more decay (TO compression)
  R16_02  body-skew d=4 t=0.05 100d longer window (stable skew)
  R16_03  body-skew d=4 t=0.05  40d  shorter window (more reactive)
  R16_04  body-skew d=4 t=0.04      tighter truncation (concentration)
  R16_05  signed_power(x,2) variant  quadratic dampening of cube
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


def body_skew(window: int) -> str:
    return (
        f"-1 * ts_mean(power(ts_zscore("
        f"(close - open) / open, {window}), 3), {window})"
    )


FACTORS: list[dict] = [
    {
        "id": "QM_R16_01",
        "category": "body-skew-d8",
        "idea": "R15_03 with decay=8 to compress P&L noise.",
        "original": "R15_03 variant",
        "expression": body_skew(60),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R16_02",
        "category": "body-skew-w100",
        "idea": "R15_03 with 100-day window for stability.",
        "original": "R15_03 longer-window variant",
        "expression": body_skew(100),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R16_03",
        "category": "body-skew-w40",
        "idea": "R15_03 with 40-day window for responsiveness.",
        "original": "R15_03 shorter-window variant",
        "expression": body_skew(40),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R16_04",
        "category": "body-skew-t04",
        "idea": "R15_03 with tighter 0.04 truncation for concentration.",
        "original": "R15_03 tighter-trunc variant",
        "expression": body_skew(60),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.04,
        },
    },
    {
        "id": "QM_R16_05",
        "category": "body-signed_power2",
        "idea": (
            "R15_03 with signed_power(.,2) instead of cube. Quadratic "
            "magnitude with preserved sign dampens outliers."
        ),
        "original": "R15_03 variant with signed_power",
        "expression": (
            "-1 * ts_mean(signed_power("
            "ts_zscore((close - open) / open, 60), 2), 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
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
