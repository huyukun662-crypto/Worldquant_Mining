"""QuantML round D18: tune trade_when conditional CoV (Family F prototype).

D17_01 was the breakthrough on alternative shape: `trade_when(volume >
ts_mean(volume, 60), -CoV(milliq, 100), -1)` reached SH=1.45 FIT=1.51,
just below the gate. This is structurally NEW -- a conditional-firing
single-field signal, distinct from Family E (multiplicative blend).

D18 grids the trade_when parameters:

  D18_01  gate: returns > 0
          fires only on up-days. Tests momentum interaction.

  D18_02  gate: volume > ts_mean(volume, 60) * 1.5
          stricter high-volume gate.

  D18_03  gate: volume < ts_mean(volume, 60)
          INVERSE -- fire on LOW-volume days.

  D18_04  gate: CoV(milliq) > ts_mean(CoV(milliq), 250)
          self-referential: fire when current illiq instability above
          its rolling average.

  D18_05  D17_01 winner @ longer volume window (W120) + decay=0
          tune the closest candidate.

All @ SUBINDUSTRY decay=4 trunc=0.05 (D18_05 has decay=0).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"


def cov(w: int = 100) -> str:
    return f"ts_std_dev({MILLIQ}, {w}) / ts_mean({MILLIQ}, {w})"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D18_01",
        "category": "trade_when-returns-pos",
        "idea": "Fire only on positive-return days. Momentum gate.",
        "original": "trade_when(returns>0, -CoV(milliq,100), -1)",
        "expression": f"trade_when(returns > 0, -1 * {cov()}, -1)",
        "settings_override": SET,
    },
    {
        "id": "QM_D18_02",
        "category": "trade_when-volume-strict",
        "idea": "Stricter high-volume gate (1.5x avg).",
        "original": "trade_when(vol>1.5avg, -CoV(milliq,100), -1)",
        "expression": (
            f"trade_when(volume > ts_mean(volume, 60) * 1.5, -1 * {cov()}, -1)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D18_03",
        "category": "trade_when-volume-low",
        "idea": "INVERSE gate -- fire on LOW-volume days only.",
        "original": "trade_when(vol<avg, -CoV(milliq,100), -1)",
        "expression": (
            f"trade_when(volume < ts_mean(volume, 60), -1 * {cov()}, -1)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D18_04",
        "category": "trade_when-self-referential",
        "idea": (
            "Fire when current illiq instability exceeds its rolling avg "
            "(self-referential gate)."
        ),
        "original": "trade_when(CoV>roll-avg, -CoV(milliq,100), -1)",
        "expression": (
            f"trade_when({cov()} > ts_mean({cov()}, 250), -1 * {cov()}, -1)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D18_05",
        "category": "trade_when-D17_01-tuned",
        "idea": "D17_01 winner tuned: volume window=120, decay=0.",
        "original": "trade_when(vol>avg120, -CoV, -1) d=0",
        "expression": (
            f"trade_when(volume > ts_mean(volume, 120), -1 * {cov()}, -1)"
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
