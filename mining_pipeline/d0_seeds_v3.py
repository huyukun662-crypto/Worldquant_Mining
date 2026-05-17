"""D0 seeds v3 — fix parameterization bug.

v2 BUG: expressions.parameterize() replaces ALL standalone integer
literals with Optuna-suggested windows in [3, 60]. This silently
corrupted the gate THRESHOLDS:
  trade_when((news_pct_90min < 1), ...)   # original
  trade_when((news_pct_90min < 58), ...)  # after parameterize (gate disabled!)

Fix: write thresholds as FLOATS (`1.0`, `0.7`, etc.) — parameterize()
skips tokens containing `.`. Only the actual tunable windows remain as
ints. Verified by reading mining_pipeline/expressions.py:121-148:

    if "." not in tok:
        if seen_ints in windows:
            tok = str(int(windows[seen_ints]))
        seen_ints += 1

So float literals are preserved verbatim.

Tunable ints in each seed:
- gate window in ts_rank(abs(news_pct_30min), W)
- decay length in ts_decay_linear(..., D)
- z-score window in ts_zscore(..., W)
- group_rank/zscore arg positions (none — group is identifier)
"""

from __future__ import annotations

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Double-gate vol-skew, PR #10's exact form (thresholds as floats)
    # =================================================================
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_120min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_60min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_10min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 30) > 0.7), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_90min < 0.5) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",

    # =================================================================
    # Tier 2 — IV asymmetry (different tenors call vs put)
    # =================================================================
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_120 - implied_volatility_put_30), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_mean_60), 5), -1)",

    # =================================================================
    # Tier 3 — Composite: IV-skew + sentiment second leg
    # =================================================================
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_buzz_ret), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(scl12_sentiment), 5), -1)",

    # =================================================================
    # Tier 4 — Composite: IV-skew + historical-vol mean-rev
    # =================================================================
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(historical_volatility_20), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(ts_zscore(historical_volatility_20, 60)), 5), -1)",

    # =================================================================
    # Tier 5 — Composite: IV-skew + valuation (D0 fundamental)
    # =================================================================
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(enterprise_value / (ebitda + 1.0)), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + group_rank(operating_income / (assets + 1.0), subindustry), 5), -1)",

    # =================================================================
    # Tier 6 — News-shock magnitude as direct signal (no IV)
    # =================================================================
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), -ts_decay_linear(rank(news_pct_30min), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), -ts_decay_linear(rank(ts_delta(news_pct_30min, 5)), 5), -1)",
    "trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8), -ts_decay_linear(rank(news_atr14), 5), -1)",
]
