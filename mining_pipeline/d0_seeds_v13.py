"""D0 seeds v13 — break the FIT-SUB tension with structurally different alphas.

After 150+ trials with the trade_when + IV+snt blend, no alpha has passed
both FIT (≥1.30) AND SUB_UNIVERSE_SHARPE (≥SH×0.43) simultaneously. The
binary trade_when gate concentrates positions on news days, hurting SUB.

v13 tries structurally different alphas:

  - Graduated weighting (instead of binary gate): scale positions by
    news intensity continuously so the alpha still trades every day
  - Cross-sub-universe regularization: subtract group_zscore residual
  - Anti-news gate (trade on LOW news days — opposite profile)
  - Different 1st leg families to break out of the IV-skew ceiling
"""

from __future__ import annotations

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Graduated news weighting (continuous, not binary gate)
    # =================================================================
    # multiplicative weight by news intensity rank
    "ts_decay_linear((1.0 + ts_rank(abs(news_pct_30min), 60)) * (rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)), 5)",
    # boosted weight only when news intensity is high
    "ts_decay_linear((1.0 + 2.0 * ts_rank(abs(news_pct_30min), 60)) * (rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)), 5)",

    # =================================================================
    # Tier 2 — Cross-sub-universe regularization
    # =================================================================
    "ts_decay_linear((rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)) - 0.5 * group_zscore(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), sector), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - 0.3 * group_mean(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 1, sector), 5)",

    # =================================================================
    # Tier 3 — Anti-news gate (trade on LOW news days)
    # =================================================================
    "trade_when(ts_rank(abs(news_pct_30min), 60) < 0.3, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",
    "trade_when(ts_rank(abs(news_pct_30min), 60) < 0.5, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",

    # =================================================================
    # Tier 4 — Different IV transformations (term-structure ratio)
    # =================================================================
    "ts_decay_linear(rank(ts_zscore(implied_volatility_call_60 - implied_volatility_put_60, 20)) + rank(snt_value), 5)",
    "ts_decay_linear(rank((implied_volatility_call_60 - implied_volatility_put_60) / (implied_volatility_mean_60 + 0.001)) + rank(snt_value), 5)",

    # =================================================================
    # Tier 5 — Add a market/sector diversifier 3rd leg
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + 0.3 * rank(group_zscore(close, sector)), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - 0.3 * rank(ts_mean(returns, 20)), 5)",

    # =================================================================
    # Tier 6 — Use cap/liquidity to balance signal across sub-universes
    # =================================================================
    "ts_decay_linear((rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)) * rank(log(cap + 1.0)), 5)",
    "ts_decay_linear((rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)) / (1.0 + ts_std_dev(returns, 20)), 5)",

    # =================================================================
    # Tier 7 — Conditional sign flip (if_else / sign-based)
    # =================================================================
    "ts_decay_linear(if_else(ts_rank(abs(news_pct_30min), 60) > 0.7, rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), rank(snt_value) - rank(implied_volatility_call_60 - implied_volatility_put_60)), 5)",

    # =================================================================
    # Tier 8 — High-coverage PV alternative as 2nd leg (no snt_value)
    # =================================================================
    "trade_when(ts_rank(abs(news_pct_30min), 60) > 0.6, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(ts_zscore(returns, 60)), 5), -1)",
    "trade_when(ts_rank(abs(news_pct_30min), 60) > 0.6, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(close / ts_mean(close, 60)), 5), -1)",
]
