"""QuantML round D17: time-series wrappers + conditional firing around CoV(milliq).

D13-D16 confirmed every alternative shape (corr, rank, skew, group-agg,
mean*std, group-relative, ts_corr-various) fails on milliq. Only the
variance-blend structure (Family E) works.

D17 wraps the proven CoV(milliq) signal with structurally distinct
outer transforms:

  D17_01  Conditional firing
          trade_when(volume > ts_mean(volume,60), -CoV(milliq,100), -1)
          Only trades on high-volume days; conditional alpha.

  D17_02  Outer decay layer
          ts_decay_linear(-CoV(milliq,100), 30)
          Time-smooths the CoV signal -- structurally different from
          decay setting (which decays the alpha, not the expression).

  D17_03  Time-series z-score
          -ts_zscore(CoV(milliq,100), 250)
          Self-normalises CoV across its 250d history.

  D17_04  Multi-scale sum
          -CoV(milliq,60) - CoV(milliq,250)
          Fast+slow CoV combined additively (DOES the additive
          dilution rule from D12 apply within the same field?).

  D17_05  Directional CoV
          CoV(milliq,100) * sign(returns)
          Switches sign with daily returns -- captures conditional
          illiquidity x return-direction interaction.

All @ SUBINDUSTRY decay=4 trunc=0.05.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"


def cov(field: str = MILLIQ, w: int = 100) -> str:
    return f"ts_std_dev({field}, {w}) / ts_mean({field}, {w})"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D17_01",
        "category": "CoV-conditional-volume",
        "idea": "trade_when high-volume gate around -CoV(milliq).",
        "original": "trade_when(vol>avg, -CoV(milliq,100), -1)",
        "expression": (
            f"trade_when(volume > ts_mean(volume, 60), -1 * {cov()}, -1)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D17_02",
        "category": "CoV-outer-decay",
        "idea": "ts_decay_linear wrapped around -CoV(milliq,100).",
        "original": "ts_decay_linear(-CoV(milliq,100), 30)",
        "expression": f"ts_decay_linear(-1 * {cov()}, 30)",
        "settings_override": SET,
    },
    {
        "id": "QM_D17_03",
        "category": "CoV-ts-zscore",
        "idea": "ts_zscore wrapped around CoV(milliq) over 250d history.",
        "original": "-ts_zscore(CoV(milliq,100), 250)",
        "expression": f"-1 * ts_zscore({cov()}, 250)",
        "settings_override": SET,
    },
    {
        "id": "QM_D17_04",
        "category": "CoV-multi-scale",
        "idea": "Sum of fast (W60) and slow (W250) CoVs -- multi-scale combination.",
        "original": "-CoV(W60)-CoV(W250)",
        "expression": f"-1 * {cov(MILLIQ, 60)} - {cov(MILLIQ, 250)}",
        "settings_override": SET,
    },
    {
        "id": "QM_D17_05",
        "category": "CoV-directional",
        "idea": "Directional CoV: CoV(milliq) * sign(returns).",
        "original": "CoV(milliq)*sign(returns)",
        "expression": f"{cov()} * sign(returns)",
        "settings_override": SET,
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
