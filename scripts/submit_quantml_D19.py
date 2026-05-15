"""QuantML round D19: tsfresh-inspired shape battery applied to milliq.

Per the zhihu p/712261324 methodology: small base set x large operator
library = many derived factors. tsfresh ships ~783 operators; we map
the 5 most likely accessible-in-FASTEXPR shapes that we have NOT yet
tried onto milliq.

  D19_01 abs_sum_of_changes        -sum(|delta(milliq)|, 100)
         Total path length of illiquidity over 100d. Stocks with
         large cumulative motion are unstable.

  D19_02 mean_abs_change           -mean(|delta(milliq)|, 100)
         Average per-day illiq change magnitude. Differs from
         abs_sum by 1/W factor, so neutralisation may favour it
         over abs_sum.

  D19_03 count_above_mean          -sum(milliq > mean(milliq), 100)
         Number of days illiq is above its 100d mean -- captures
         persistent-elevated-illiq regime stocks.

  D19_04 autocorrelation lag-1     -ts_corr(milliq, delay(milliq,1), 100)
         Illiquidity persistence. High autocorr -> stable regime;
         low or negative -> regime-changing.

  D19_05 ratio_beyond_2sigma       -sum(|x - mean| > 2sigma, 100)
         Density of >2-sigma illiq events in the last 100 days.
         Tail-event frequency, distinct from level or std.

All @ SUBINDUSTRY decay=4 trunc=0.05 (Family E sweet-spot).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"

SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D19_01",
        "category": "milliq-abs-sum-changes",
        "idea": "tsfresh abs_sum_of_changes: total path length of illiquidity.",
        "original": "-sum(|delta(milliq,1)|, 100)",
        "expression": f"-1 * ts_sum(abs(ts_delta({MILLIQ}, 1)), 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D19_02",
        "category": "milliq-mean-abs-change",
        "idea": "tsfresh mean_abs_change: average per-day illiq change magnitude.",
        "original": "-mean(|delta(milliq,1)|, 100)",
        "expression": f"-1 * ts_mean(abs(ts_delta({MILLIQ}, 1)), 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D19_03",
        "category": "milliq-count-above-mean",
        "idea": (
            "tsfresh count_above_mean: number of days illiq > mean(100). "
            "Encoded as sum of indicator using less()."
        ),
        "original": "-sum(milliq>mean(milliq,100), 100)",
        "expression": (
            f"-1 * ts_sum(less(ts_mean({MILLIQ}, 100), {MILLIQ}), 100)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D19_04",
        "category": "milliq-autocorr-lag1",
        "idea": "tsfresh autocorrelation lag-1: illiquidity persistence.",
        "original": "-ts_corr(milliq, delay(milliq,1), 100)",
        "expression": (
            f"-1 * ts_corr({MILLIQ}, ts_delay({MILLIQ}, 1), 100)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D19_05",
        "category": "milliq-ratio-beyond-2sigma",
        "idea": (
            "tsfresh ratio_beyond_r_sigma (r=2): density of >2sigma illiq "
            "events in last 100 days."
        ),
        "original": "-sum(|milliq-mean|>2sigma, 100)",
        "expression": (
            f"-1 * ts_sum(greater(abs({MILLIQ} - ts_mean({MILLIQ}, 100)), "
            f"2 * ts_std_dev({MILLIQ}, 100)), 100)"
        ),
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
