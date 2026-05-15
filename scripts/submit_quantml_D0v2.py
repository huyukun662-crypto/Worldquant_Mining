"""QuantML round D0v2: delay=0 obscure fields on TOP3000 simulation.

D0 on TOP200 universe was 0/5 (universe too small per CLAUDE.md
finding #8). Test whether the same delay=0 news/sentiment fields can
be used on TOP3000 simulation -- the field metadata says TOP200 but
WQ Brain may accept the cross-universe combination.

  D0v2_01  CoV(news_indx_perf, 100) on TOP3000
  D0v2_02  CoV blend: news_indx_perf x snt_value on TOP3000
  D0v2_03  MAC blend: news_high_exc_stddev x snt_buzz on TOP3000
  D0v2_04  trade_when wrap on CoV(news_indx_perf) on TOP3000 d=0
  D0v2_05  blend with milliq: CoV(milliq) x CoV(news_indx_perf)
           on TOP3000 - cross-category (liq + news)

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


def mac(field: str, w: int = 100) -> str:
    return f"ts_mean(abs(ts_delta({field}, 1)), {w})"


SET = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.05,
}

FACTORS: list[dict] = [
    {
        "id": "QM_D0v2_01",
        "category": "news_indx_perf-CoV-TOP3000",
        "idea": "CoV(news_indx_perf) on TOP3000 (field metadata=TOP200).",
        "original": "-CoV(news_indx_perf, 100) TOP3000",
        "expression": f"-1 * {cov('news_indx_perf')}",
        "settings_override": SET,
    },
    {
        "id": "QM_D0v2_02",
        "category": "news-snt-blend-TOP3000",
        "idea": "Family E pattern: news x sentiment on TOP3000.",
        "original": "-CoV(news_indx_perf)*CoV(snt_value) TOP3000",
        "expression": (
            f"-1 * {cov('news_indx_perf')} * {cov('snt_value')}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D0v2_03",
        "category": "news-snt-MAC-TOP3000",
        "idea": "MAC blend: news high-vol x sentiment buzz on TOP3000.",
        "original": "-MAC(news_high_exc_stddev)*MAC(snt_buzz) TOP3000",
        "expression": (
            f"-1 * {mac('news_high_exc_stddev')} * {mac('snt_buzz')}"
        ),
        "settings_override": SET,
    },
    {
        "id": "QM_D0v2_04",
        "category": "news_indx_perf-trade_when-TOP3000",
        "idea": "Family F pattern: trade_when wrap on CoV(news_indx_perf).",
        "original": "trade_when(vol>avg, -CoV(news_indx_perf), -1) TOP3000",
        "expression": (
            f"trade_when(volume > ts_mean(volume, 120), -1 * "
            f"{cov('news_indx_perf')}, -1)"
        ),
        "settings_override": {**SET, "decay": 0},
    },
    {
        "id": "QM_D0v2_05",
        "category": "milliq-news-CoV-cross",
        "idea": (
            "Cross-category Family E: CoV(milliq) x CoV(news_indx_perf). "
            "Liq instability x news-attention instability."
        ),
        "original": "-CoV(milliq)*CoV(news_indx_perf) TOP3000",
        "expression": f"-1 * {cov(MILLIQ)} * {cov('news_indx_perf')}",
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
