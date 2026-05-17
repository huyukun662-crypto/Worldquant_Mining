"""Seed library of D0 (delay=0) factor templates.

Integer literals embedded in each expression become Optuna-tunable
windows via `expressions.parameterize()`. All fields used here have
been verified D0-available on account 2445560398@qq.com via
constants/data_fields_cache_USA_0_TOP3000.json (1,225 fields total at
D0 TOP3000):
  - PV (64)
  - fundamental (660): assets, enterprise_value, ebitda, operating_income,
    debt, sales, equity, eps, ...
  - news (336): news_pct_{30sec..120min}, news_atr14, news_cap, ...
  - analyst (90): anl4_*
  - option (64): implied_volatility_{call,put,mean}_{10..1080},
    historical_volatility_{10..180}
  - socialmedia (11): snt_buzz, snt_buzz_ret, snt_value, scl12_buzz, ...

PRIOR EVIDENCE GUIDING SEED CHOICE:
  - PR #11 (this account, archived): PV-only D0 mining capped at
    SH ≈ 1.30 across 343 trials. The D0 submit gate is SH > 2.0.
    Therefore PV-only seeds will NOT clear the bar — we need
    non-PV D0 fields.
  - PR #10 (this account): vol-skew × news-shock structure on D1
    cleared SH > 2.0 (alpha vR5lg6Wr SH=2.01). The fields it used
    (implied_volatility_call/put, news_pct_*, historical_volatility_*)
    are ALL available at D0 on this account.
  - WQ Brain training materials cite `-ts_zscore(enterprise_value /
    ebitda, 63)` as a canonical valuation alpha (SH ≈ 2.58 reference).
    `enterprise_value` and `ebitda` are D0 fundamental fields here.
  - 2026-05-17 D0 probe (alpha_id 88OPp8z7): `rank(close - open)`
    has SH = -0.79 → reversion is the right sign at D0 USA.
"""

from __future__ import annotations

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Vol-skew × news-shock (PR #10 winner pattern, ported D1→D0)
    # =================================================================
    # Pure vol-skew (call - put), short tenor, with cross-sectional rank
    "rank(implied_volatility_call_60 - implied_volatility_put_60)",
    "rank(implied_volatility_call_30 - implied_volatility_put_30)",
    "rank(implied_volatility_call_90 - implied_volatility_put_90)",
    "rank(implied_volatility_call_120 - implied_volatility_put_120)",
    "-rank(implied_volatility_call_60 - implied_volatility_put_60)",
    # Vol-skew with decay
    "ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5)",
    "ts_decay_linear(rank(implied_volatility_call_30 - implied_volatility_put_30), 5)",
    "-ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5)",
    # IV change z-score (skew dynamics)
    "-ts_zscore(implied_volatility_call_60 - implied_volatility_put_60, 20)",
    "ts_zscore(implied_volatility_call_30 - implied_volatility_put_30, 20)",

    # Vol-skew × news-shock gate (the canonical PR #10 structure)
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_120min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when(ts_rank(abs(news_pct_30min), 60) > 0.8, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",
    "trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8), -ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60), 5), -1)",

    # =================================================================
    # Tier 2 — Valuation reversion (fundamental fields at D0)
    # =================================================================
    # Canonical EV/EBITDA z-score reversion (research-quoted SH≈2.58)
    "-ts_zscore(enterprise_value / (ebitda + 1), 63)",
    "-ts_zscore(enterprise_value / (ebitda + 1), 120)",
    "-group_rank(enterprise_value / (ebitda + 1), subindustry)",
    "-group_zscore(enterprise_value / (ebitda + 1), subindustry)",
    # Other valuation multiples
    "-ts_zscore(enterprise_value / (sales + 1), 63)",
    "-group_rank(enterprise_value / (sales + 1), subindustry)",
    "-group_rank(cap / (ebitda + 1), subindustry)",
    "-group_rank(cap / (operating_income + 1), subindustry)",
    "-group_rank(cap / (equity + 1), subindustry)",  # P/B
    # Quality (profitability) × value composite
    "group_rank(operating_income / (assets + 1), subindustry) + (-group_rank(enterprise_value / (ebitda + 1), subindustry))",

    # =================================================================
    # Tier 3 — Realized vol reversion (option-cat field, D0)
    # =================================================================
    "-ts_zscore(historical_volatility_20, 60)",
    "-ts_zscore(historical_volatility_60, 120)",
    "-rank(historical_volatility_10 / (historical_volatility_60 + 0.001))",
    "ts_decay_linear(-rank(historical_volatility_10 / (historical_volatility_60 + 0.001)), 5)",

    # =================================================================
    # Tier 4 — Sentiment / social-media shock
    # =================================================================
    "-ts_zscore(snt_buzz_ret, 20)",
    "-ts_zscore(snt_value, 20)",
    "trade_when(snt_buzz > ts_mean(snt_buzz, 20) * 1.5, -ts_zscore(snt_value, 10), -1)",
    "trade_when(scl12_buzz > ts_mean(scl12_buzz, 20) * 1.5, -ts_zscore(scl12_sentiment, 10), -1)",
    "-rank(snt_buzz_ret) * sign(returns)",

    # =================================================================
    # Tier 5 — PV reversion (kept as baseline; PR #11 showed SH≤1.30)
    # =================================================================
    "-rank((close - open) / ((high - low) + 0.001))",
    "-rank((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001))",
    "rank((vwap - close) / (vwap + close))",
]
