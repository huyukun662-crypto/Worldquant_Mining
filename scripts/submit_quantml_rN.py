"""QuantML round "N": 3 factors avoiding the two winning families.

Existing 3 viables cluster into 2 structural families:
  family A  variance asymmetry on OHLC channel  (R6_01, OA24)
  family B  session-mean decomposition           (R8_03)

This round delivers 3 new shapes that avoid both:

  QM_N1   volume conditioned on return sign       conditional MEAN of
                                                  VOLUME, not std/price
  QM_N2   gap-fade correlation                    corr(overnight, intraday)
                                                  -- corr pair, not mean diff
  QM_N3   sub-industry decoupling                 -corr(name_ret, peer_ret)
                                                  -- cross-stock correlation

All three are distinct from R6_01 / OA24 / R8_03 in their core
operator (no std-of-asymmetric, no mean-of-session-diff).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_N1",
        "category": "volume-cond-asym",
        "idea": (
            "Up-day mean volume minus down-day mean volume over "
            "60d. Captures volume distribution asymmetry: positive = "
            "buying volume dominates = institutional accumulation; "
            "negative = distribution. Long positive. VOLUME input "
            "is orthogonal to all variance/mean-of-price factors."
        ),
        "original": "Mean(Vol*(Ret>0),60) - Mean(Vol*(Ret<0),60)",
        "expression": (
            "ts_mean(volume * greater(returns, 0), 60) "
            "- ts_mean(volume * less(returns, 0), 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_N2",
        "category": "gap-fade-corr",
        "idea": (
            "60-day correlation between overnight gap and intraday "
            "return: corr(open/delay(close,1)-1, close/open-1, 60). "
            "Negative = gap-fade pattern (gaps tend to be filled "
            "intraday). Long names with strong gap-fade behavior "
            "(short-term reversal premium at the session level). "
            "Different from R8_03 which is mean(overnight)-mean(intra); "
            "this is the cross-session CORRELATION, not the mean diff."
        ),
        "original": "Corr(Overnight, Intraday, 60)",
        "expression": (
            "-1 * ts_corr("
            "open / ts_delay(close, 1) - 1, "
            "close / open - 1, "
            "60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_N3",
        "category": "peer-decoupling",
        "idea": (
            "Negative 60-day correlation of name returns with their "
            "sub-industry peer mean returns. Long names whose "
            "returns DECOUPLE from peers (idiosyncratic news -> "
            "trend continuation premium). Uses group_mean as a "
            "cross-sectional reference; structurally orthogonal "
            "to time-series-only factors."
        ),
        "original": "-Corr(Ret, GroupMean(Ret, SubInd), 60)",
        "expression": (
            "-1 * ts_corr(returns, "
            "group_mean(returns, 1, subindustry), 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
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
