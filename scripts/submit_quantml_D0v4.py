"""QuantML round D0v4: sign flips + delay=0 fields as trade_when GATE.

D0/D0v2/D0v3 0/15: every -1*-prefixed news/snt expression goes negative.
Implication: WITHOUT the -1*, direction is positive. Also, putting
delay=0 fields in the GATE position of trade_when (rather than as
base signal) sidesteps the TO contamination -- the base remains the
proven CoV(milliq) signal.

  D0v4_01  Flip sign: +CoV(snt_buzz, 100)  -- direct positive
           (D0v3_05 was -0.29 with -1*, so +0.29 without).

  D0v4_02  Flip sign: +ts_mean(snt_value, 100) -- direct positive
           (D0v3_02 was -0.56 with -1*, so +0.56 without).

  D0v4_03  Subtractive: CoV(milliq, 100) - CoV(snt_buzz, 100)
           contrast between two CoV signals.

  D0v4_04  GATE form: trade_when(snt_buzz > ts_mean(snt_buzz, 60),
                                 -CoV(milliq,100), -1)
           Use snt_buzz as a yes/no gate; base signal remains milliq.

  D0v4_05  GATE form: trade_when(news_indx_perf > 0,
                                 -CoV(milliq,100), -1)
           News-positive-return days only.

All @ TOP3000 SUBINDUSTRY decay=4 trunc=0.05 (D0v4_04/05 d=0).
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
        "id": "QM_D0v4_01",
        "category": "snt_buzz-CoV-positive",
        "idea": "Positive CoV of buzz (flip of D0v3_05).",
        "original": "+CoV(snt_buzz, 100)",
        "expression": cov("snt_buzz"),
        "settings_override": SET,
    },
    {
        "id": "QM_D0v4_02",
        "category": "snt_value-mean-positive",
        "idea": "Direct positive mean of negative-sentiment field.",
        "original": "+ts_mean(snt_value, 100)",
        "expression": "ts_mean(snt_value, 100)",
        "settings_override": SET,
    },
    {
        "id": "QM_D0v4_03",
        "category": "milliq-snt_buzz-diff",
        "idea": "Contrastive: CoV(milliq) - CoV(snt_buzz).",
        "original": "CoV(milliq) - CoV(snt_buzz)",
        "expression": f"{cov(MILLIQ)} - {cov('snt_buzz')}",
        "settings_override": SET,
    },
    {
        "id": "QM_D0v4_04",
        "category": "snt_buzz-gate-trade_when",
        "idea": "snt_buzz as gate, milliq CoV as base signal.",
        "original": "trade_when(snt_buzz>avg, -CoV(milliq), -1) d=0",
        "expression": (
            f"trade_when(snt_buzz > ts_mean(snt_buzz, 60), "
            f"-1 * {cov(MILLIQ)}, -1)"
        ),
        "settings_override": {**SET, "decay": 0},
    },
    {
        "id": "QM_D0v4_05",
        "category": "news-positive-gate-trade_when",
        "idea": "News-positive days as gate, milliq CoV as base.",
        "original": "trade_when(news_indx_perf>0, -CoV(milliq), -1) d=0",
        "expression": (
            f"trade_when(news_indx_perf > 0, -1 * {cov(MILLIQ)}, -1)"
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
