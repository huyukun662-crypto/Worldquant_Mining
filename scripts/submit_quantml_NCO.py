"""QuantML round NCO (No Close/Open): extend Families E & F using
high/low/volume/vwap as the second leg or gate, no close/open allowed.

Constraint: never reference close or open fields. Allowed PV fields:
high, low, volume, vwap, adv20, plus obscure mdl77/snt fields.

  NCO_01  HL-range CoV as second leg of Family E:
          -CoV(high-low, 100) * CoV(milliq, 100)

  NCO_02  Volume CoV as second leg:
          -CoV(volume, 100) * CoV(milliq, 100)

  NCO_03  VWAP CoV as second leg:
          -CoV(vwap, 100) * CoV(milliq, 100)

  NCO_04  Triple with HL range added to D12_04 blend:
          -CoV(milliq) * CoV(bap20d) * CoV(high-low)

  NCO_05  Family F with new-high gate (no close/open):
          trade_when(high > ts_delay(ts_max(high, 20), 1),
                     -CoV(milliq, 100), -1)

All @ TOP3000 SUBINDUSTRY decay=4 trunc=0.05.
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


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

# CoV of (high-low) — use the raw subtraction directly.
def cov_diff(a: str, b: str, w: int = 100) -> str:
    return f"ts_std_dev({a} - {b}, {w}) / ts_mean({a} - {b}, {w})"


FACTORS: list[dict] = [
    {
        "id": "QM_NCO_01",
        "category": "HL-range-CoV-x-milliq",
        "idea": "Daily range (high-low) CoV blended with milliq CoV.",
        "original": "-CoV(high-low,100) * CoV(milliq,100)",
        "expression": f"-1 * {cov_diff('high', 'low')} * {cov(MILLIQ)}",
        "settings_override": SET,
    },
    {
        "id": "QM_NCO_02",
        "category": "volume-CoV-x-milliq",
        "idea": "Volume CoV blended with milliq CoV (no close/open).",
        "original": "-CoV(volume,100) * CoV(milliq,100)",
        "expression": f"-1 * {cov('volume')} * {cov(MILLIQ)}",
        "settings_override": SET,
    },
    {
        "id": "QM_NCO_03",
        "category": "vwap-CoV-x-milliq",
        "idea": "VWAP CoV blended with milliq CoV.",
        "original": "-CoV(vwap,100) * CoV(milliq,100)",
        "expression": f"-1 * {cov('vwap')} * {cov(MILLIQ)}",
        "settings_override": SET,
    },
    {
        "id": "QM_NCO_04",
        "category": "triple-milliq-bap-HLrange",
        "idea": "Triple product: milliq * bap20d * (high-low) CoVs.",
        "original": "-CoV(milliq)*CoV(bap20d)*CoV(high-low)",
        "expression": (
            f"-1 * {cov(MILLIQ)} * {cov(BAP)} * {cov_diff('high', 'low')}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_NCO_05",
        "category": "new-high-gate-trade_when",
        "idea": "Family F with 20-day-new-high gate (no close/open).",
        "original": "trade_when(high>ts_delay(ts_max(high,20),1),-CoV(milliq),-1)",
        "expression": (
            f"trade_when(high > ts_delay(ts_max(high, 20), 1), "
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
