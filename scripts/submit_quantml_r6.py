"""QuantML round 6: OHLC candlestick-style structures.

Return-based factors cap at SH ~ 0.94 on USA TOP3000 after industry-
neut. OA24 (from the prior OpenAlpha task) hit SH=1.47 by using
high/low vs prior close -- an OHLC channel orthogonal to close-only
returns. Round 6 builds five candlestick-style factors that all live
in that OHLC channel.

  R6_01  intraday body asymmetric variance
  R6_02  candle body / range ratio (doji frequency)
  R6_03  upper-shadow on up-days only
  R6_04  close position within high-low range
  R6_05  signed-power signed body
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R6_01",
        "category": "body-var-asymmetry",
        "idea": (
            "Intraday body (close-open) downside-vs-upside std over "
            "100d, normalised by open. Same shape as R4_02 but on "
            "intraday body, not close-to-close returns. Should add "
            "OHLC-channel information to the SH=0.94 R4_02 result."
        ),
        "original": "Std((C-O)/O * (C<O), 100) - Std((C-O)/O * (C>O), 100)",
        "expression": (
            "ts_std_dev((close - open) / open * less(close - open, 0), 100) "
            "- ts_std_dev((close - open) / open * greater(close - open, 0), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R6_02",
        "category": "body-range-ratio",
        "idea": (
            "Average ratio of candle body to total range over 60d. "
            "Persistent high body-fraction = decisive moves; "
            "persistent low = indecision / mean-reverting. Sign "
            "negative: short decisive-trend names (momentum is "
            "already priced in)."
        ),
        "original": "Mean(|C-O| / (H-L), 60)",
        "expression": (
            "-1 * ts_mean(abs(close - open) / (high - low + 0.001), 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R6_03",
        "category": "upper-shadow-on-up",
        "idea": (
            "Mean of upper shadow ((high-close)/close) computed only "
            "on up-days (close>open). Persistent high upper shadows "
            "on up-days = sellers fade the rally = bearish; short."
        ),
        "original": "Mean((H-C)/C * (C>O), 60)",
        "expression": (
            "-1 * ts_mean((high - close) / close "
            "* greater(close - open, 0), 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R6_04",
        "category": "close-in-range-position",
        "idea": (
            "Average (close-low)/(high-low) over 60d -- close's "
            "position in the daily range. Persistent closing near "
            "high = buying pressure dominates = momentum signal; "
            "long it."
        ),
        "original": "Mean((C-L)/(H-L), 60)",
        "expression": (
            "ts_mean((close - low) / (high - low + 0.001), 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R6_05",
        "category": "signed-body-power",
        "idea": (
            "Average signed_power((close-open)/open, 0.5) over 60d. "
            "Concave transform of the daily body emphasises moderate "
            "moves and dampens outliers; persistent positive bias "
            "= institutional accumulation."
        ),
        "original": "Mean(SignedPow((C-O)/O, 0.5), 60)",
        "expression": (
            "ts_mean(signed_power((close - open) / open, 0.5), 60)"
        ),
        "settings_override": {
            "decay": 4,
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
