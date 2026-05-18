"""D0 v9 — diverse 2nd-leg candidates beyond snt_value.

After confirming snt_value has cov=1.0 (not a coverage issue), the
CONCENTRATED_WEIGHT FAIL on the IV-skew + snt_value family is likely
structural: when both legs strongly agree at the extremes, a few names
absorb most of the long/short weight even after truncation.

v9 strategy — find a 2nd-leg with different cross-sectional shape that
keeps SH high while flattening the weight distribution:

  - sentiment alternatives: snt_buzz, snt_buzz_bfl, scl12_buzz,
    scl12_sentiment  (different cuts of social-media data)
  - analyst estimate fields: anl4_*_est (forward estimates)
  - 3-leg with pv: + rank(close) or rank(returns) for size/recent-return
  - news high-cov fields

Each seed expression is a complete alpha; mine_d0_until_pass.py engine
tunes integer literals + (universe, decay, truncation, neutralization).
"""

from __future__ import annotations

# This file is just a seed list. The runner is mine_d0_until_pass.py
SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Sentiment alternates (different from snt_value)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_buzz), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(snt_buzz), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_buzz_bfl), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(scl12_buzz), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(scl12_sentiment), 5)",

    # =================================================================
    # Tier 2 — Analyst forward estimates as 2nd leg
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(anl4_dez1afv4_est), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(anl4_dez1afv4_est), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(anl4_dez1afv4_est - anl4_dez1afv4_preest), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(anl4_dez1qfv4_est), 5)",

    # =================================================================
    # Tier 3 — IV-skew + PV (returns / close-based, full coverage)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(returns), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(ts_mean(returns, 20)), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(close / ts_mean(close, 60)), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(ts_mean(returns, 5)), 5)",

    # =================================================================
    # Tier 4 — 3-leg: snt_value + analyst as orthogonal 3rd
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + rank(anl4_dez1afv4_est - anl4_dez1afv4_preest), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) - rank(returns), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + rank(close / ts_mean(close, 60)), 5)",

    # =================================================================
    # Tier 5 — Pure non-sentiment combinations (no snt_value)
    # =================================================================
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(anl4_dez1afv4_est - anl4_dez1afv4_preest) - rank(returns), 5)",
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) - rank(ts_mean(returns, 5)) + rank(anl4_dez1afv4_est), 5)",
]
