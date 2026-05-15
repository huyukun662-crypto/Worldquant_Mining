"""QuantML round D0v3: smoothed delay=0 fields to control event-driven TO.

D0/D0v2 0/10: news/sentiment delay=0 fields are spiky -- CoV directly
on them produces turnover 0.4-0.6. D0v3 wraps the same fields with
smoothing layers (ts_decay_linear, inner ts_mean of input) before
applying our proven shapes.

  D0v3_01  Outer decay smoothing:
           ts_decay_linear(-CoV(news_indx_perf, 100), 60)

  D0v3_02  Direct level (no CoV):
           -ts_mean(snt_value, 100)

  D0v3_03  Pre-smoothed input then CoV:
           -CoV(ts_mean(news_indx_perf, 20), 100)

  D0v3_04  Cross-family blend on smoothed news:
           CoV(milliq) x CoV(smoothed news_indx_perf)

  D0v3_05  snt_buzz (volume-like, less spiky) CoV.

All @ TOP3000 SUBINDUSTRY decay=4 trunc=0.05.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

MILLIQ = "mdl77_liquidityriskfactor_milliq"


def cov(field: str, w: int = 100) -> str:
    return f"ts_std_dev({field}, {w}) / ts_mean({field}, {w})"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D0v3_01",
        "category": "news-CoV-outer-decay",
        "idea": "Outer decay-smoothing of news CoV to compress TO.",
        "original": "ts_decay_linear(-CoV(news_indx_perf,100), 60)",
        "expression": (
            f"ts_decay_linear(-1 * {cov('news_indx_perf')}, 60)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D0v3_02",
        "category": "snt_value-direct-mean",
        "idea": "Direct slow mean of negative-sentiment score.",
        "original": "-ts_mean(snt_value, 100)",
        "expression": "-1 * ts_mean(snt_value, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D0v3_03",
        "category": "news-pre-smoothed-CoV",
        "idea": "Pre-smooth input with ts_mean(20) before CoV(100).",
        "original": "-CoV(ts_mean(news_indx_perf,20),100)",
        "expression": (
            f"-1 * ts_std_dev(ts_mean(news_indx_perf, 20), 100) "
            f"/ ts_mean(ts_mean(news_indx_perf, 20), 100)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D0v3_04",
        "category": "milliq-news-smoothed-blend",
        "idea": (
            "Cross-family blend on smoothed news: "
            "CoV(milliq) x CoV(smoothed news_indx_perf)."
        ),
        "original": "-CoV(milliq)*CoV(smoothed news_indx_perf)",
        "expression": (
            f"-1 * {cov(MILLIQ)} * "
            f"ts_std_dev(ts_mean(news_indx_perf, 20), 100) "
            f"/ ts_mean(ts_mean(news_indx_perf, 20), 100)"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D0v3_05",
        "category": "snt_buzz-CoV",
        "idea": "CoV of social-media buzz volume -- volume-like, less spiky.",
        "original": "-CoV(snt_buzz, 100)",
        "expression": f"-1 * {cov('snt_buzz')}",
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
