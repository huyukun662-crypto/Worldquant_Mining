"""D0 seeds v4 — drop trade_when, multi-leg blends, group_neutralize.

v1-v3 evidence (129 trials, best SH=1.71):
- All top 10 alphas are variants of `ts_decay_linear(rank(IV_call_60 -
  IV_put_60), N)` on TOP3000 + INDUSTRY.
- top 6 are WITHOUT trade_when — the gate actually hurts SH (gate
  concentrates trading and narrows the effective sample).
- sub-universe SH (~0.39) is the main blocker even when IS-SH is 1.4-1.7.

v4 strategy:
1. NO trade_when (it hurt SH consistently).
2. Multi-leg blends (IV-skew + sentiment / + fundamental quality) —
   different orthogonal signals to boost FIT.
3. Multi-tenor IV (call_30 - put_120 etc.) — different vol-surface shapes.
4. group_neutralize(rank(signal), subindustry) — explicit sub-universe
   protection.
5. IV term-structure slope (call_30 / call_180) — short-vs-long IV.
6. Sentiment + fundamental crossover — no IV at all.
"""

from __future__ import annotations

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — IV-skew + sentiment blend (no gate)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(snt_buzz_ret), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(scl12_sentiment), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(ts_zscore(snt_value, 20)), 5)",

    # =================================================================
    # Tier 2 — IV-skew + fundamental quality blend
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(enterprise_value / (ebitda + 1.0)), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(operating_income / (assets + 1.0)), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + group_rank(operating_income / (assets + 1.0), subindustry), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - group_zscore(enterprise_value / (ebitda + 1.0), subindustry), 5)",

    # =================================================================
    # Tier 3 — Multi-tenor IV asymmetry (different shapes)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_put_60), 5)",
    "ts_decay_linear(rank(implied_volatility_call_120 - implied_volatility_put_30), 5)",
    "ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_mean_120), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 / (implied_volatility_put_60 + 0.001)), 5)",
    "ts_decay_linear(rank((implied_volatility_call_60 - implied_volatility_put_60) / (implied_volatility_mean_60 + 0.001)), 5)",

    # =================================================================
    # Tier 4 — IV term structure (call_short / call_long)
    # =================================================================
    "ts_decay_linear(-rank(implied_volatility_call_30 / (implied_volatility_call_180 + 0.001)), 5)",
    "ts_decay_linear(rank(implied_volatility_mean_30 - implied_volatility_mean_180), 5)",
    "ts_decay_linear(-rank(implied_volatility_call_30 / (implied_volatility_call_360 + 0.001)), 5)",

    # =================================================================
    # Tier 5 — group_neutralize for sub-universe protection
    # =================================================================
    "group_neutralize(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), subindustry)",
    "group_neutralize(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), industry)",
    "group_rank(ts_decay_linear(implied_volatility_call_60 - implied_volatility_put_60, 5), subindustry)",
    "group_zscore(ts_decay_linear(implied_volatility_call_60 - implied_volatility_put_60, 5), subindustry)",

    # =================================================================
    # Tier 6 — IV-skew minus realized-vol (skew vs hist)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(historical_volatility_60), 5)",
    "ts_decay_linear(rank((implied_volatility_call_60 - implied_volatility_put_60) - historical_volatility_30), 5)",

    # =================================================================
    # Tier 7 — Pure fundamental Z-score reversion (no IV at all)
    # =================================================================
    "-ts_zscore(enterprise_value / (ebitda + 1.0), 63)",
    "-group_zscore(enterprise_value / (ebitda + 1.0), subindustry)",
    "-group_zscore(enterprise_value / (sales + 1.0), subindustry)",
    "group_rank(operating_income / (assets + 1.0), subindustry) - group_rank(enterprise_value / (ebitda + 1.0), subindustry)",
]
