"""D0 seeds v8 — structural fixes for CONCENTRATED_WEIGHT and sub-universe SH.

Confirmed via direct submit of alpha mLqa8wX2 (SH=1.83 FIT=1.45):
  WQ submit returned 403 with FAILs on:
    1. LOW_SHARPE (1.83 < 2.0)
    2. CONCENTRATED_WEIGHT (limit/value absent — structural, not weight-cap)
    3. LOW_SUB_UNIVERSE_SHARPE (0.77 < 0.79)

v8 attacks all three with STRUCTURAL transforms rather than weight tuning:

  - Double-rank `rank(rank(a) + rank(b))` flattens the sum distribution
    and should fix CONCENTRATED_WEIGHT (the sum a+b piles up at extremes
    when both legs agree, creating concentrated weights post-truncation).
  - `scale()` L1-normalizes; explicit weight cap.
  - `group_zscore(.., subindustry)` / `group_rank(.., subindustry)`
    wrapping should boost LOW_SUB_UNIVERSE_SHARPE by per-group standardization.
  - 3-leg with fundamental quality (EV/EBITDA, op_income/assets) brings
    orthogonal cross-section info.
"""

from __future__ import annotations

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Double-rank (target: fix CONCENTRATED_WEIGHT)
    # =================================================================
    "ts_decay_linear(rank(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)), 5)",

    # =================================================================
    # Tier 2 — scale() wrapper (L1 normalize)
    # =================================================================
    "ts_decay_linear(scale(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)), 5)",
    "scale(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5))",

    # =================================================================
    # Tier 3 — winsorize / quantile-clip extreme weights
    # =================================================================
    "winsorize(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), std=4)",
    "ts_decay_linear(winsorize(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), std=4), 5)",

    # =================================================================
    # Tier 4 — group_zscore wrapper (target: boost LOW_SUB_UNIVERSE_SHARPE)
    # =================================================================
    "group_zscore(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), subindustry)",
    "group_rank(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), subindustry)",
    "group_zscore(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), industry)",

    # =================================================================
    # Tier 5 — Group operations INSIDE the legs (per-group rank)
    # =================================================================
    "ts_decay_linear(group_rank(implied_volatility_call_60 - implied_volatility_put_60, subindustry) + group_rank(snt_value, subindustry), 5)",
    "ts_decay_linear(group_rank(implied_volatility_call_60 - implied_volatility_put_60, industry) + group_rank(snt_value, industry), 5)",

    # =================================================================
    # Tier 6 — Fundamental quality 3rd leg (orthogonal info)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - rank(enterprise_value / (ebitda + 1.0)), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + rank(operating_income / (assets + 1.0)), 5)",
    "ts_decay_linear(rank(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - rank(enterprise_value / (ebitda + 1.0))), 5)",

    # =================================================================
    # Tier 7 — Combined: double-rank + group neutralize wrapper
    # =================================================================
    "group_zscore(ts_decay_linear(rank(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)), 5), subindustry)",
    "group_rank(ts_decay_linear(rank(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value)), 5), industry)",

    # =================================================================
    # Tier 8 — Sentiment-time-series transforms (ts_zscore, ts_delta)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + ts_zscore(snt_value, 5), 5)",
    "ts_decay_linear(rank(ts_zscore(implied_volatility_call_60 - implied_volatility_put_60, 20)) + rank(ts_zscore(snt_value, 5)), 5)",
]
