"""QuantML round 3: lean into the asymmetric-tail / vol-of-vol axis.

Round-1/2 best singletons hit SH ≈ 0.78-0.84, all with very low
turnover -- the signals are clean but underleveraged on their own.
OA24 from the OpenAlpha task (SH=1.47) proved that DIFFERENCE-OF-TAIL
shapes at long windows is the working pattern.

Five new structurally distinct factors that target high SH:

  R3_01 downside semi-vol (return-based) 60d
  R3_02 downside-minus-upside semi-vol diff (100d, return-based variant of OA24)
  R3_03 vol-of-vol (20-of-60)
  R3_04 lottery / return-volatility coupling 60d (ts_corr(returns, abs(returns)))
  R3_05 rank composite of the two best single signals so far
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R3_01",
        "category": "downside-semivol",
        "idea": (
            "60-day downside semi-deviation: ts_std_dev of "
            "min(returns, 0). Short names with high downside-only "
            "volatility -- the low-vol anomaly's downside-tail form."
        ),
        "original": "Std(Min(Ret($close,1), 0), 60)",
        "expression": "-1 * ts_std_dev(min(returns, 0), 60)",
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R3_02",
        "category": "tail-asymmetry",
        "idea": (
            "Downside-minus-upside semi-deviation over 100 days, on "
            "returns. Long names with relatively more downside vol "
            "(risk premium), short upside-heavy. Same shape as OA24 "
            "but driven by returns instead of OHLC."
        ),
        "original": (
            "Std(Min(Ret($close,1),0),100) - Std(Max(Ret($close,1),0),100)"
        ),
        "expression": (
            "ts_std_dev(min(returns, 0), 100) "
            "- ts_std_dev(max(returns, 0), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R3_03",
        "category": "vol-of-vol",
        "idea": (
            "20-day std of the 60-day std of returns. Short names "
            "with unstable volatility (regime-uncertain) -- a risk-"
            "premium variant orthogonal to plain idio-vol."
        ),
        "original": "Std(Std(Ret($close,1), 20), 60)",
        "expression": "-1 * ts_std_dev(ts_std_dev(returns, 20), 60)",
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R3_04",
        "category": "return-vol-coupling",
        "idea": (
            "ts_corr(returns, abs(returns), 60) -- correlation between "
            "signed return and its magnitude. Positive coupling = "
            "up-days are bigger than down-days = lottery-like = "
            "over-bought by retail; short it."
        ),
        "original": "Corr(Ret($close,1), Abs(Ret($close,1)), 60)",
        "expression": "-1 * ts_corr(returns, abs(returns), 60)",
        "settings_override": {
            "decay": 0,
            "neutralization": "MARKET",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R3_05",
        "category": "rank-composite",
        "idea": (
            "Rank composite of (i) OA24-style tail asymmetry on "
            "low/high-vs-prior-close and (ii) negative kurtosis. "
            "Combining two orthogonal weak signals into a stronger "
            "one via cross-sectional ranking."
        ),
        "original": "Rank(OA24) + Rank(NegKurt) average",
        "expression": (
            "(rank("
            "ts_std_dev(low/ts_delay(close,1) - 1, 100) "
            "- ts_std_dev(high/ts_delay(close,1) - 1, 100)"
            ") + rank("
            "-1 * ts_mean(power(ts_zscore(returns, 60), 4), 60)"
            ")) / 2"
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
