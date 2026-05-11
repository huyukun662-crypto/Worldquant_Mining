"""QuantML round 11: target SH>1.35, TO<0.15.

After 10 rounds, 3 factors pass the new gate (R6_01, OA24, R8_03).
R10 produced two near-misses worth flipping/retuning:

  R10_01 peer-rel-mean      SH=-1.06 -> flip should give +1.06
  R10_04 intraday-body-skew SH= 1.07 -> retune window for +0.28 SH

R11 plan:
  R11_01  peer-rel-mean (flipped, longer window)
  R11_02  intraday-body-skew on 100d (was 60d)
  R11_03  vwap-anchored asym variance (different channel from R6_01)
  R11_04  high-vs-vwap, vwap-vs-low intraday pressure diff
  R11_05  peer-rel session-mean (R8_03 minus peer subindustry mean)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R11_01",
        "category": "peer-rel-mean-flip",
        "idea": (
            "Flip R10_01 sign and lengthen to 120d. Peer-relative "
            "MOMENTUM continuation: long names whose cumulative "
            "60-120d excess vs sub-industry peers is positive."
        ),
        "original": "+Mean(Ret - GroupMean(Ret, SubInd), 120)",
        "expression": (
            "ts_mean(returns - group_mean(returns, 1, subindustry), 120)"
        ),
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R11_02",
        "category": "intraday-body-skew-100",
        "idea": (
            "R10_04 retuned to 100d (was 60d). Long-window skew of "
            "intraday body more stable; should compress noise."
        ),
        "original": "-Skew((C-O)/O, 100)",
        "expression": (
            "-1 * ts_mean(power(ts_zscore("
            "(close - open) / open, 100), 3), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "MARKET",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R11_03",
        "category": "vwap-asym-variance",
        "idea": (
            "Asym variance on (close-vwap)/vwap over 100d. Same "
            "shape as R6_01 but on the vwap-anchor channel -- "
            "different from intraday body and OHLC tails."
        ),
        "original": "AsymStd((C-VWAP)/VWAP, 100)",
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
        "id": "QM_R11_04",
        "category": "hv-vl-pressure-diff",
        "idea": (
            "60-day mean of (high-vwap)/vwap minus mean of "
            "(vwap-low)/vwap. Positive when upper range exceeds "
            "lower range relative to vwap -- buying pressure "
            "indicator. Long it."
        ),
        "original": "Mean((H-V)/V, 60) - Mean((V-L)/V, 60)",
        "expression": (
            "ts_mean((high - vwap) / vwap, 60) "
            "- ts_mean((vwap - low) / vwap, 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R11_05",
        "category": "peer-rel-session",
        "idea": (
            "R8_03 (overnight - intraday) minus its sub-industry "
            "peer mean. Strip the peer-group session bias; keep "
            "only the name-specific session-asymmetry signal. "
            "Different from R8_03 by removing group component."
        ),
        "original": "R8_03 - GroupMean(R8_03, SubInd)",
        "expression": (
            "(ts_mean(open / ts_delay(close, 1) - 1, 60) "
            "- ts_mean(close / open - 1, 60)) "
            "- group_mean("
            "ts_mean(open / ts_delay(close, 1) - 1, 60) "
            "- ts_mean(close / open - 1, 60), "
            "1, subindustry)"
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
