"""D0 seeds v14 — targeted attacks on LOW_SUB_UNIVERSE_SHARPE.

After 200+ trials, the trade_when + IV+snt blend caps at chk=5/8 with
mutually exclusive FIT-pass and SUB-pass clusters. The SUB-pass cluster
has SH 1.50-1.55 FIT 1.06-1.29 (always fails FIT).

v14 keeps trade_when (essential for low TO and CW pass) but attacks SUB
via different structural changes:

  - Slower underlying signal (ts_mean of IV_skew before rank) for
    smoother behavior across sub-universes
  - group_neutralize wrap by SECTOR (instead of SUBINDUSTRY)
  - Liquidity-balanced 3rd leg (rank(volume) or rank(adv20))
  - Returns-mean reversion 3rd leg
  - Slower decay (longer N + slower WQ decay) to flatten signal
"""

from __future__ import annotations

GATE_OR = "(ts_rank(abs(news_pct_30min), 60) > 0.6)"
GATE_OR_TIGHT = "(ts_rank(abs(news_pct_30min), 60) > 0.8)"

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Slower underlying IV-skew (ts_mean before rank)
    # =================================================================
    f"trade_when({GATE_OR}, ts_decay_linear(rank(ts_mean(implied_volatility_call_60 - implied_volatility_put_60, 5)) + rank(snt_value), 5), -1)",
    f"trade_when({GATE_OR}, ts_decay_linear(rank(ts_mean(implied_volatility_call_60 - implied_volatility_put_60, 10)) + rank(ts_mean(snt_value, 5)), 5), -1)",

    # =================================================================
    # Tier 2 — Sector-neutralized wrap (different from group_zscore)
    # =================================================================
    f"group_neutralize(trade_when({GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1), sector)",
    f"group_neutralize(trade_when({GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1), subindustry)",

    # =================================================================
    # Tier 3 — Liquidity-balanced (volume / adv20 3rd leg)
    # =================================================================
    f"trade_when({GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + 0.2 * rank(log(adv20 + 1.0)), 5), -1)",
    f"trade_when({GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - 0.2 * rank(log(cap + 1.0)), 5), -1)",

    # =================================================================
    # Tier 4 — Mean-reversion 3rd leg (returns based)
    # =================================================================
    f"trade_when({GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - 0.3 * rank(ts_mean(returns, 20)), 5), -1)",
    f"trade_when({GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + 0.3 * rank(ts_zscore(close, 60)), 5), -1)",

    # =================================================================
    # Tier 5 — Slower N + slower WQ decay (smooth across SUB)
    # =================================================================
    f"trade_when({GATE_OR_TIGHT}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 60), -1)",
    f"trade_when({GATE_OR_TIGHT}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 90), -1)",

    # =================================================================
    # Tier 6 — Conditional anti-news (LOW news days, opposite profile)
    # =================================================================
    f"trade_when(ts_rank(abs(news_pct_30min), 60) < 0.4, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",

    # =================================================================
    # Tier 7 — Combined news condition (both high gate AND fundamental tilt)
    # =================================================================
    f"trade_when({GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + 0.5 * rank(snt_value) + 0.3 * rank(close / ts_mean(close, 20)), 5), -1)",
]
