"""QuantML round NEW: structurally distinct shapes (Families G/H/J/K/M).

NCO/NCO2 stacked 5 more Family-E variants. NEW explores shapes that
are NOT just "multiplicative blend of mean-normalised variances":
ranks, time-deltas, z-scores, asymmetric variances, variance ratios.
Still no close/open fields.

  NEW_01  Cross-sect rank product (Family G):
          -rank(CoV(milliq,100)) * rank(CoV(bap20d,100))

  NEW_02  Momentum of variance (Family H):
          -ts_delta(CoV(milliq,100), 20) * CoV(bap20d, 100)

  NEW_03  Z-score blend (Family J):
          -ts_zscore(milliq, 250) * CoV(bap20d, 100)

  NEW_04  Asymmetric upside variance (Family K):
          -ts_mean(max(ts_delta(milliq,1),0)^2, 100)
              * CoV(bap20d, 100)

  NEW_05  Short/long variance ratio (Family M):
          -CoV(milliq, 30) / CoV(milliq, 250)

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

FACTORS: list[dict] = [
    {
        "id": "QM_NEW_01",
        "category": "rank-product (G)",
        "idea": "Cross-sect rank of CoVs instead of magnitude product.",
        "original": "-rank(CoV(milliq))*rank(CoV(bap20d))",
        "expression": f"-1 * rank({cov(MILLIQ)}) * rank({cov(BAP)})",
        "settings_override": SET,
    },
    {
        "id": "QM_NEW_02",
        "category": "delta-CoV (H)",
        "idea": "Momentum of CoV: ts_delta(CoV(milliq), 20) * CoV(bap20d).",
        "original": "-ts_delta(CoV(milliq,100),20) * CoV(bap20d,100)",
        "expression": (
            f"-1 * ts_delta({cov(MILLIQ)}, 20) * {cov(BAP)}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_NEW_03",
        "category": "ts_zscore (J)",
        "idea": "Time-series zscore of milliq blended with bap20d CoV.",
        "original": "-ts_zscore(milliq, 250) * CoV(bap20d, 100)",
        "expression": (
            f"-1 * ts_zscore({MILLIQ}, 250) * {cov(BAP)}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_NEW_04",
        "category": "asymmetric-upside-var (K)",
        "idea": "Only worsening illiquidity (delta>0) variance, times bap20d CoV.",
        "original": "-ts_mean(max(delta(milliq,1),0)^2,100) * CoV(bap20d,100)",
        "expression": (
            f"-1 * ts_mean(power(max(ts_delta({MILLIQ}, 1), 0), 2), 100) "
            f"* {cov(BAP)}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_NEW_05",
        "category": "var-ratio-short-long (M)",
        "idea": "Short/long variance term-structure of milliq.",
        "original": "-CoV(milliq,30) / CoV(milliq,250)",
        "expression": f"-1 * {cov(MILLIQ, 30)} / {cov(MILLIQ, 250)}",
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
