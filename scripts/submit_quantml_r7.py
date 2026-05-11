"""QuantML round 7: more channels for the asymmetric-variance shape.

The shape `ts_std_dev(x * less, N) - ts_std_dev(x * greater, N)` on
100d wins on two channels so far:

    OA24      x = low/delay(close,1)-1, high/delay(close,1)-1   SH=1.47
    R6_01     x = (close-open)/open                              SH=1.51

Round 7 introduces five new channels for the same shape:

  R7_01  overnight gap                  (open/delay(close,1) - 1)
  R7_02  upper shadow conditioned on    (high - close)/close
         day sign (close <> open)
  R7_03  lower shadow conditioned on    (close - low)/close
         day sign
  R7_04  close vs vwap (intraday tilt)  (close - vwap)/vwap
  R7_05  high/low vs same-day open      (variant of OA24 with
                                          open-anchor not close)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R7_01",
        "category": "overnight-gap-asym",
        "idea": (
            "Overnight-gap asymmetric variance 100d. Long names whose "
            "down-gaps are more variable than up-gaps -- earns the "
            "overnight risk premium that close-to-close returns miss."
        ),
        "original": "Std(Gap * (Gap<0), 100) - Std(Gap * (Gap>0), 100)",
        "expression": (
            "ts_std_dev((open / ts_delay(close, 1) - 1) "
            "* less(open - ts_delay(close, 1), 0), 100) "
            "- ts_std_dev((open / ts_delay(close, 1) - 1) "
            "* greater(open - ts_delay(close, 1), 0), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R7_02",
        "category": "upper-shadow-asym",
        "idea": (
            "Upper-shadow variance 100d split by day sign: on down "
            "days minus on up days. Persistent upper-shadow variance "
            "on down days = aborted rallies into the close = tail-"
            "risk premium signal; long it."
        ),
        "original": "Std(UpShadow*(C<O), 100) - Std(UpShadow*(C>O), 100)",
        "expression": (
            "ts_std_dev((high - close) / close "
            "* less(close - open, 0), 100) "
            "- ts_std_dev((high - close) / close "
            "* greater(close - open, 0), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R7_03",
        "category": "lower-shadow-asym",
        "idea": (
            "Lower-shadow variance 100d split by day sign: on down "
            "days minus on up days. Captures buying-into-weakness "
            "behaviour."
        ),
        "original": "Std(LoShadow*(C<O), 100) - Std(LoShadow*(C>O), 100)",
        "expression": (
            "ts_std_dev((close - low) / close "
            "* less(close - open, 0), 100) "
            "- ts_std_dev((close - low) / close "
            "* greater(close - open, 0), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R7_04",
        "category": "close-vwap-asym",
        "idea": (
            "Close-vs-vwap asymmetric variance 100d. Splits by sign "
            "of (close - vwap): days closing below vwap (institutional "
            "selling pressure) vs above. Long names whose below-vwap "
            "moves are more variable."
        ),
        "original": "Std((C-Vwap)/Vwap * (C<Vwap), 100) - Std(... (C>Vwap))",
        "expression": (
            "ts_std_dev((close - vwap) / vwap "
            "* less(close - vwap, 0), 100) "
            "- ts_std_dev((close - vwap) / vwap "
            "* greater(close - vwap, 0), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R7_05",
        "category": "hl-vs-open-asym",
        "idea": (
            "Like OA24 but anchored on same-day OPEN instead of "
            "previous-day close. Std of (low/open - 1) minus std of "
            "(high/open - 1) over 100d -- separates the day's "
            "drawdown variance from rally variance, with no overnight-"
            "gap component."
        ),
        "original": "Std(L/O - 1, 100) - Std(H/O - 1, 100)",
        "expression": (
            "ts_std_dev(low / open - 1, 100) "
            "- ts_std_dev(high / open - 1, 100)"
        ),
        "settings_override": {
            "decay": 0,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
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
