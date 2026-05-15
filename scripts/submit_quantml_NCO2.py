"""QuantML round NCO2: HL-range as first leg + alt gates (no close/open).

NCO showed that Family E generalises beyond mdl77: HL-range and
volume both work as the second leg with milliq. NCO2 explores
whether milliq is also replaceable, and tries non-volume gates for
Family F that don't reference close/open.

  NCO2_01  Quadruple blend:
           -CoV(milliq)*CoV(bap20d)*CoV(HL)*CoV(volume)

  NCO2_02  No-milliq triple (only PV + bap20d):
           -CoV(bap20d)*CoV(HL)*CoV(volume)

  NCO2_03  HL-range pair-only (no obscure fields):
           -CoV(HL,100)*CoV(volume,100)

  NCO2_04  Family F with HL-range gate:
           trade_when(high - low > ts_mean(high - low, 60),
                      -CoV(milliq, 100), -1)

  NCO2_05  Family F with adv20 gate:
           trade_when(adv20 > ts_mean(adv20, 120),
                      -CoV(milliq, 100), -1)

All @ TOP3000 SUBINDUSTRY decay=4 trunc=0.05 (gate variants decay=0).
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


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

HL = "high - low"

FACTORS: list[dict] = [
    {
        "id": "QM_NCO2_01",
        "category": "quadruple-milliq-bap-HL-vol",
        "idea": "Quadruple variance blend: milliq, bap20d, HL-range, volume.",
        "original": "-CoV(milliq)*CoV(bap20d)*CoV(HL)*CoV(volume)",
        "expression": (
            f"-1 * {cov(MILLIQ)} * {cov(BAP)} * "
            f"{cov_expr(HL)} * {cov('volume')}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_NCO2_02",
        "category": "no-milliq-triple",
        "idea": "Triple WITHOUT milliq: bap20d * HL * volume.",
        "original": "-CoV(bap20d)*CoV(HL)*CoV(volume)",
        "expression": (
            f"-1 * {cov(BAP)} * {cov_expr(HL)} * {cov('volume')}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_NCO2_03",
        "category": "pure-PV-pair-HL-volume",
        "idea": "PV-only pair: HL-range CoV * volume CoV (no obscure fields).",
        "original": "-CoV(HL,100)*CoV(volume,100)",
        "expression": f"-1 * {cov_expr(HL)} * {cov('volume')}",
        "settings_override": SET,
    },
    {
        "id": "QM_NCO2_04",
        "category": "HL-range-gate-trade_when",
        "idea": "Family F with HL-range > avg60 as gate.",
        "original": "trade_when(HL>avg60(HL),-CoV(milliq,100),-1)",
        "expression": (
            f"trade_when((high - low) > ts_mean(high - low, 60), "
            f"-1 * {cov(MILLIQ)}, -1)"
        ),
        "settings_override": {**SET, "decay": 0},
    },
    {
        "id": "QM_NCO2_05",
        "category": "adv20-gate-trade_when",
        "idea": "Family F with adv20 > avg120(adv20) as gate.",
        "original": "trade_when(adv20>avg120(adv20),-CoV(milliq,100),-1)",
        "expression": (
            f"trade_when(adv20 > ts_mean(adv20, 120), "
            f"-1 * {cov(MILLIQ)}, -1)"
        ),
        "settings_override": {**SET, "decay": 0},
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
