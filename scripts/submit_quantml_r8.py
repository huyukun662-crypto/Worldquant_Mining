"""QuantML round 8: 5 more structurally distinct families with
asymmetric/economic content (not asym-variance shape).

Round 7 (auto-corr / CV / sign-streak / rank-reversal / volume-shock)
all topped at SH ~ 0.5 -- structurally orthogonal but economically
weak. Round 8 tries asymmetric/economic structures that still
diverge mathematically from R6_01/OA24:

  R8_01  omega-like gain/loss diff   mean(upside) - mean(downside)
  R8_02  big-down-day frequency      ts_mean(less(returns, -0.02), 60)
  R8_03  overnight-vs-intraday       mean(overnight) - mean(intraday)
  R8_04  industry-relative long mom  12-1 minus subindustry peer mean
  R8_05  total shadow vs body        (range - body) averaged 60d
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R8_01",
        "category": "omega-gain-loss-diff",
        "idea": (
            "Omega-ratio cousin: mean upside return minus mean "
            "absolute downside return, 100d. Captures asymmetric "
            "expected payoff (not variance), so structurally "
            "orthogonal to R6_01/OA24's variance asymmetry. Long "
            "positive (more upside than downside)."
        ),
        "original": "Mean(Ret*(Ret>0),100) - Mean(-Ret*(Ret<0),100)",
        "expression": (
            "ts_mean(returns * greater(returns, 0), 100) "
            "- ts_mean(-1 * returns * less(returns, 0), 100)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R8_02",
        "category": "big-down-frequency",
        "idea": (
            "Fraction of days with returns < -2% over a 60-day "
            "window. Pure indicator count, no variance. Long names "
            "with high big-down frequency (downside risk premium "
            "via crash-probability)."
        ),
        "original": "Mean(I(Ret < -0.02), 60)",
        "expression": "ts_mean(less(returns, -0.02), 60)",
        "settings_override": {
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R8_03",
        "category": "overnight-vs-intraday",
        "idea": (
            "60-day mean overnight return (open/delay(close,1)-1) "
            "minus 60-day mean intraday return (close/open-1). "
            "Decomposes the return into sessions; persistent gap-"
            "up + intraday-sell = distributed selling -> long."
        ),
        "original": "Mean(Overnight,60) - Mean(Intraday,60)",
        "expression": (
            "ts_mean(open / ts_delay(close, 1) - 1, 60) "
            "- ts_mean(close / open - 1, 60)"
        ),
        "settings_override": {
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R8_04",
        "category": "industry-relative-mom",
        "idea": (
            "12-1 momentum minus the sub-industry peer mean. "
            "Industry-neut at the settings level already removes "
            "industry-mean but not sub-industry mean; this strips "
            "the latter explicitly. Long names ahead of peers."
        ),
        "original": "Mom12_1 - GroupMean(Mom12_1, SubIndustry)",
        "expression": (
            "((close / ts_delay(close, 252) - 1) "
            "- (close / ts_delay(close, 21) - 1)) "
            "- group_mean("
            "(close / ts_delay(close, 252) - 1) "
            "- (close / ts_delay(close, 21) - 1), "
            "1, subindustry)"
        ),
        "settings_override": {
            "decay": 8,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R8_05",
        "category": "shadow-vs-body",
        "idea": (
            "60-day mean of (high - low - |close - open|) / close = "
            "total shadow length normalised. High shadow = "
            "indecision and reversal pressure. Short it."
        ),
        "original": "Mean(((H-L) - |C-O|) / C, 60)",
        "expression": (
            "-1 * ts_mean(((high - low) - abs(close - open)) / close, 60)"
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
