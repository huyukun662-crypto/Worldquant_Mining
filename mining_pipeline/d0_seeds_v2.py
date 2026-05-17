"""D0 seeds v2 — target SH > 2.0 / FIT > 1.3.

Built from v1 pass-1 evidence: the trade_when news-shock single-gate +
IV-skew + ts_decay_linear family hits SH ≈ 1.5-1.7 / FIT ≈ 1.1-1.24
but not the D0 gate. PR #10's actual winner at D1 used the DOUBLE
gate (news_pct_90min < 1) ∧ news_shock, plus a second blended signal.

This file expands the winning structure:
1. Double-gate variants (PR #10 exact form)
2. Wider IV asymmetry: call_short - put_long and vice versa
3. Composite signals: IV-skew + sentiment / + realized-vol mean-rev
4. Composite signals: IV-skew + EV/EBITDA reversion (D0 fundamental)
"""

from __future__ import annotations

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Double-gate vol-skew (PR #10 exact form, ported D1→D0)
    # =================================================================
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_120min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_60min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_10min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 30) > 0.7), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",

    # =================================================================
    # Tier 2 — IV asymmetry (different tenors call vs put)
    # =================================================================
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_120 - implied_volatility_put_30), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_mean_60), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 / (implied_volatility_put_60 + 0.001)), 5), -1)",

    # =================================================================
    # Tier 3 — Composite: IV-skew + sentiment second leg
    # =================================================================
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_buzz_ret), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(scl12_sentiment), 5), -1)",

    # =================================================================
    # Tier 4 — Composite: IV-skew + historical-vol mean-rev
    # =================================================================
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(historical_volatility_20), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(ts_zscore(historical_volatility_20, 60)), 5), -1)",

    # =================================================================
    # Tier 5 — Composite: IV-skew + valuation (D0 fundamental)
    # =================================================================
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(enterprise_value / (ebitda + 1)), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + group_rank(operating_income / (assets + 1), subindustry), 5), -1)",

    # =================================================================
    # Tier 6 — News-shock magnitude as direct signal (no IV)
    # =================================================================
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), -ts_decay_linear(rank(news_pct_30min), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), -ts_decay_linear(rank(ts_delta(news_pct_30min, 5)), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), -ts_decay_linear(rank(news_atr14), 5), -1)",
]
