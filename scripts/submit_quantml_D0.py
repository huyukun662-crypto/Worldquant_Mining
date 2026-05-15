"""QuantML round D0: delay=0 obscure fields on TOP200 universe.

Per user request: mine factors using delay=0 fields. The cache shows
1225 fields with delay=0 in their metadata; the rare ones (userCount
<= 20, coverage >= 0.9) live in news/socialmedia/pv categories and are
universally TOP200 (not TOP3000 like Family E milliq).

Apply our proven shapes (CoV, MAC blend, trade_when wrap) to the most
promising delay=0 fields:

  D0_01  CoV(news_indx_perf, 100)
         stock-vs-SPX news-day relative return CoV.
  D0_02  CoV blend: news_indx_perf x snt_value
         news-impact instability x negative-sentiment instability.
  D0_03  MAC blend: news_high_exc_stddev x snt_buzz
         news high-vol x sentiment-buzz mean-abs-change.
  D0_04  trade_when wrap on news_indx_perf CoV (Family F style)
  D0_05  CoV(news_high_exc_stddev, 100)
         price-excess-vol on news days, scale-free.

All on TOP200 (delay=0 fields only available there), delay=1 simulation
(account tier blocks delay=0 sim), SUBINDUSTRY neut, decay=4, t=0.05.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


def cov(field: str, w: int = 100) -> str:
    return f"ts_std_dev({field}, {w}) / ts_mean({field}, {w})"


def mac(field: str, w: int = 100) -> str:
    return f"ts_mean(abs(ts_delta({field}, 1)), {w})"


SET = {
    "universe": "TOP200", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D0_01",
        "category": "news_indx_perf-CoV",
        "idea": (
            "CoV of news-day stock-vs-SPX relative return. News-attention "
            "instability proxy on TOP200."
        ),
        "original": "-CoV(news_indx_perf, 100)",
        "expression": f"-1 * {cov('news_indx_perf')}",
        "settings_override": SET,
    },
    {
        "id": "QM_D0_02",
        "category": "news-snt-CoV-blend",
        "idea": (
            "Family E pattern on TOP200: -CoV(news_indx_perf) * "
            "CoV(snt_value). News-impact x sentiment-instability product."
        ),
        "original": "-CoV(news_indx_perf)*CoV(snt_value)",
        "expression": (
            f"-1 * {cov('news_indx_perf')} * {cov('snt_value')}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D0_03",
        "category": "news-snt-MAC-blend",
        "idea": (
            "MAC blend on TOP200: news_high_exc_stddev x snt_buzz."
        ),
        "original": "-MAC(news_high_exc_stddev)*MAC(snt_buzz)",
        "expression": (
            f"-1 * {mac('news_high_exc_stddev')} * {mac('snt_buzz')}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D0_04",
        "category": "news_indx_perf-trade_when",
        "idea": (
            "Family F pattern on TOP200: trade_when(vol > avg120, "
            "-CoV(news_indx_perf), -1) at decay=0."
        ),
        "original": "trade_when(vol>avg, -CoV(news_indx_perf), -1)",
        "expression": (
            f"trade_when(volume > ts_mean(volume, 120), -1 * "
            f"{cov('news_indx_perf')}, -1)"
        ),
        "settings_override": {**SET, "decay": 0},
    },
    {
        "id": "QM_D0_05",
        "category": "news_high_exc_stddev-CoV",
        "idea": (
            "CoV of news-day price-excess-stddev. Already a stddev "
            "measure -- CoV is std-of-std (4th moment)."
        ),
        "original": "-CoV(news_high_exc_stddev, 100)",
        "expression": f"-1 * {cov('news_high_exc_stddev')}",
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
