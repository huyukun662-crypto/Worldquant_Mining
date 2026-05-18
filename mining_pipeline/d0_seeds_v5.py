"""D0 seeds v5 — focused exploration around alpha 6XRd003O (SH=1.83 FIT=1.41).

v4 evidence: the winning structure is
  ts_decay_linear(rank(IV_call_60 - IV_put_60) + rank(snt_value), N)
on TOP3000 + INDUSTRY. Other sentiment fields (snt_buzz_ret,
scl12_sentiment, ts_zscore(snt_value, 20)) all underperform.

Champion (alpha 6XRd003O):
  optimized: ts_decay_linear(rank(IV_call_60 - IV_put_60) + rank(snt_value), 54)
  settings:  TOP3000 / delay=0 / decay=6 / truncation=0.1 / INDUSTRY / ON
  result:    SH=1.83 (need 2.0)  FIT=1.41  TO=0.165  SubU_SH=0.77 (need 0.79)
  fail:      LOW_SHARPE (+0.17 needed), CONCENTRATED_WEIGHT (likely truncation
             0.1 too lax), LOW_SUB_UNIVERSE_SHARPE (+0.02 needed)

v5 plan — fine-tune around the champion:
1. Weighted blends (boost IV-skew or snt_value weight)
2. Triple-leg with realized-vol (hist-vol mean-reversion)
3. Different IV tenor combinations with snt_value
4. snt_value as ts_zscore'd (vs raw)
5. snt_value combined with group_neutralize
6. Trigger CONCENTRATED_WEIGHT fix via tighter truncation (in setting space, not seed)
"""

from __future__ import annotations

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Exact champion + simple variants (re-tune via tighter trunc)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5)",

    # =================================================================
    # Tier 2 — Weighted blends (different IV / snt weighting)
    # =================================================================
    "ts_decay_linear(2.0 * rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + 2.0 * rank(snt_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + 0.5 * rank(snt_value), 5)",
    "ts_decay_linear(3.0 * rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5)",

    # =================================================================
    # Tier 3 — Triple leg (add hist-vol short, term-structure, etc.)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - rank(historical_volatility_20), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - rank(historical_volatility_60), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + rank(snt_social_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - rank(implied_volatility_call_30 / (implied_volatility_call_180 + 0.001)), 5)",

    # =================================================================
    # Tier 4 — IV tenor variants paired with snt_value
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_put_30) + rank(snt_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_90 - implied_volatility_put_90) + rank(snt_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_120 - implied_volatility_put_120) + rank(snt_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_put_60) + rank(snt_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_120 - implied_volatility_put_30) + rank(snt_value), 5)",

    # =================================================================
    # Tier 5 — snt_value processed differently
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + ts_zscore(snt_value, 5), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(ts_delta(snt_value, 1)), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(ts_mean(snt_value, 5)), 5)",

    # =================================================================
    # Tier 6 — group_neutralize wrapping (sub-universe boost)
    # =================================================================
    "group_neutralize(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), industry)",
    "group_neutralize(ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), subindustry)",
    "ts_decay_linear(group_rank(implied_volatility_call_60 - implied_volatility_put_60, subindustry) + group_rank(snt_value, subindustry), 5)",

    # =================================================================
    # Tier 7 — Negative-direction variants (in case sign was wrong)
    # =================================================================
    "ts_decay_linear(-rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(snt_value), 5)",
]
