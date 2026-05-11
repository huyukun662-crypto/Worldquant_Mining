"""QuantML round 2: 5 new structurally distinct factors.

None of the round-1 categories (amplitude / median / MAD / kurtosis /
Amihud) is reused. New structures introduced:

    R2_01  idiosyncratic vol  - residual variance after market mean
    R2_02  recency-of-extreme - ordinal position of recent high vs low
    R2_03  12-1 momentum      - long-horizon trend minus short reversal
    R2_04  volume anomaly     - volume relative to its long-window mean
    R2_05  third moment       - skewness of returns

All use longer windows (60-252d) to keep turnover low.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R2_01",
        "category": "idio-vol",
        "idea": (
            "Idiosyncratic volatility (60d residual std). After "
            "subtracting the market-mean return, names with higher "
            "residual variance carry more idiosyncratic risk; the "
            "USA-equity premium says these underperform -> short."
        ),
        "original": "Std(Resid(Ret, MktRet), 60)",
        "expression": (
            "-1 * ts_std_dev(returns - group_mean(returns, 1, market), 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R2_02",
        "category": "recency-extreme",
        "idea": (
            "Ordinal recency of 60-day low vs high. "
            "ts_arg_min(close,60) - ts_arg_max(close,60) is positive "
            "when the low is more recent than the high (recent "
            "drawdown); long those names (mean reversion)."
        ),
        "original": "ArgMin($close, 60) - ArgMax($close, 60)",
        "expression": "ts_arg_min(close, 60) - ts_arg_max(close, 60)",
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R2_03",
        "category": "momentum-12-1",
        "idea": (
            "Classical 12-1 momentum (Jegadeesh-Titman / Asness). Long "
            "names with high 252-day return excluding the most recent "
            "21 days (avoid short-term reversal). Robust premium on "
            "USA large/mid-caps."
        ),
        "original": "Ret($close, 252) - Ret($close, 21)",
        "expression": (
            "(close / ts_delay(close, 252) - 1) "
            "- (close / ts_delay(close, 21) - 1)"
        ),
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R2_04",
        "category": "volume-anomaly",
        "idea": (
            "Recent volume relative to its 60-day mean. Persistent "
            "high relative volume = investor attention -> short side "
            "(attention-driven names underperform on average)."
        ),
        "original": "Mean($volume, 5) / Mean($volume, 60)",
        "expression": "-1 * ts_mean(volume, 5) / ts_mean(volume, 60)",
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R2_05",
        "category": "third-moment",
        "idea": (
            "60-day skewness of returns. Positive-skew (lottery-like) "
            "names are over-bought by retail; short positive skew. "
            "Pure shape statistic -> MARKET neutralization."
        ),
        "original": "Skew(Ret($close, 1), 60)",
        "expression": (
            "-1 * ts_mean(power(ts_zscore(returns, 60), 3), 60)"
        ),
        "settings_override": {
            "decay": 0,
            "neutralization": "MARKET",
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
