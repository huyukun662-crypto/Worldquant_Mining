"""QuantML round NEW2: extend Family K + try Family N (co-jump correlation).

NEW_04 confirmed Family K (asymmetric semi-variance) works at SH=1.88.
NEW2 explores: (a) downside mirror, (b) K with proven HL leg from NCO,
(c) double-half-variance, (d) asymmetric on bap20d, and (e) a new
structural shape -- Family N -- using ts_correlation of jumps.

  NEW2_01  Downside semi-variance (mirror of NEW_04):
           -ts_mean(min(delta(milliq,1),0)^2, 100) * CoV(bap20d, 100)

  NEW2_02  Family K with HL-range second leg:
           -ts_mean(max(delta(milliq,1),0)^2, 100) * CoV(HL, 100)

  NEW2_03  Co-jump correlation (Family N):
           -ts_correlation(delta(milliq,1), delta(bap20d,1), 100)
              * CoV(volume, 100)

  NEW2_04  Asymmetric semi-var on bap20d:
           -CoV(milliq, 100) * ts_mean(max(delta(bap20d,1),0)^2, 100)

  NEW2_05  Double half-variance (no CoV leg):
           -ts_mean(max(delta(milliq,1),0)^2, 100)
              * ts_mean(max(delta(bap20d,1),0)^2, 100)

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


def cov_expr(expr: str, w: int = 100) -> str:
    return f"ts_std_dev({expr}, {w}) / ts_mean({expr}, {w})"


def upside_var(field: str, w: int = 100) -> str:
    return f"ts_mean(power(max(ts_delta({field}, 1), 0), 2), {w})"


def downside_var(field: str, w: int = 100) -> str:
    return f"ts_mean(power(min(ts_delta({field}, 1), 0), 2), {w})"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_NEW2_01",
        "category": "downside-semi-var (K mirror)",
        "idea": "Mirror of NEW_04: downside semi-var of milliq.",
        "original": "-down_var(milliq) * CoV(bap20d)",
        "expression": f"-1 * {downside_var(MILLIQ)} * {cov(BAP)}",
        "settings_override": SET,
    },
    {
        "id": "QM_NEW2_02",
        "category": "K-HL-leg",
        "idea": "Family K with HL-range second leg (best NCO second-leg).",
        "original": "-upside_var(milliq) * CoV(HL)",
        "expression": f"-1 * {upside_var(MILLIQ)} * {cov_expr('high - low')}",
        "settings_override": SET,
    },
    {
        "id": "QM_NEW2_03",
        "category": "co-jump-correlation (N)",
        "idea": "Co-jump corr of milliq/bap20d deltas, blended with vol CoV.",
        "original": "-ts_corr(d(milliq),d(bap20d),100) * CoV(volume,100)",
        "expression": (
            f"-1 * ts_correlation(ts_delta({MILLIQ}, 1), "
            f"ts_delta({BAP}, 1), 100) * {cov('volume')}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_NEW2_04",
        "category": "K-on-bap20d",
        "idea": "Asymmetric semi-var on bap20d instead of milliq.",
        "original": "-CoV(milliq) * upside_var(bap20d)",
        "expression": f"-1 * {cov(MILLIQ)} * {upside_var(BAP)}",
        "settings_override": SET,
    },
    {
        "id": "QM_NEW2_05",
        "category": "double-half-variance",
        "idea": "Pure double half-variance on milliq and bap20d.",
        "original": "-upside_var(milliq) * upside_var(bap20d)",
        "expression": f"-1 * {upside_var(MILLIQ)} * {upside_var(BAP)}",
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
