"""D0 v10 — combine news trade_when gate (v1-v3) with snt_value blend (v4-v9).

KEY DISCOVERY across v1-v3c:
  53 alphas PASS CONCENTRATED_WEIGHT, all using
    trade_when((news_pct_90min < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.8),
               ts_decay_linear(rank(IV_call_60 - IV_put_60), 5), -1)
  Best SH = 1.53 (KPnrrdJp).

v4-v9 dropped trade_when and reached SH=1.90 (xAevZYMb) on IV+snt_value
blend but ALL fail CONCENTRATED_WEIGHT structurally.

The trade_when gate trims trading to high-news days → fewer concentrated
positions per sector → CONCENTRATED_WEIGHT PASS.

v10 combines:
  trade_when(news_gate, IV_skew + snt_value, -1)
The gate maintains CONCENTRATED_WEIGHT PASS; snt_value brings SH above
the IV-skew-only ceiling of 1.53. Target SH > 2.0.
"""

from __future__ import annotations

# Common news gate expression
NEWS_GATE_AND = "((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8))"
NEWS_GATE_OR = "(ts_rank(abs(news_pct_30min), 60) > 0.8)"

SEED_EXPRESSIONS: list[str] = [
    # =================================================================
    # Tier 1 — Core combination: news gate + IV+snt blend
    # =================================================================
    f"trade_when({NEWS_GATE_AND}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",
    f"trade_when({NEWS_GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",

    # =================================================================
    # Tier 2 — Weighted blends inside the gate
    # =================================================================
    f"trade_when({NEWS_GATE_AND}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + 2.0 * rank(snt_value), 5), -1)",
    f"trade_when({NEWS_GATE_AND}, ts_decay_linear(2.0 * rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",
    f"trade_when({NEWS_GATE_OR}, ts_decay_linear(2.0 * rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",

    # =================================================================
    # Tier 3 — Looser gates (more trade days, may keep CW pass)
    # =================================================================
    f"trade_when(ts_rank(abs(news_pct_30min), 60) > 0.6, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",
    f"trade_when(ts_rank(abs(news_pct_30min), 60) > 0.5, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",

    # =================================================================
    # Tier 4 — Tighter gates (sparser, may PASS more checks)
    # =================================================================
    f"trade_when(ts_rank(abs(news_pct_30min), 60) > 0.9, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",

    # =================================================================
    # Tier 5 — Alternative news gates
    # =================================================================
    f"trade_when(ts_rank(news_sent_30min, 60) > 0.8, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",
    f"trade_when(ts_rank(abs(news_pct_90min), 60) > 0.7, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value), 5), -1)",

    # =================================================================
    # Tier 6 — Gate + 3-leg (snt + small HV)
    # =================================================================
    f"trade_when({NEWS_GATE_AND}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + 0.1 * rank(-historical_volatility_30), 5), -1)",
    f"trade_when({NEWS_GATE_OR}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_value) + 0.1 * rank(-historical_volatility_10), 5), -1)",

    # =================================================================
    # Tier 7 — Gate + snt-only (no IV; may be lower SH but CW-safe)
    # =================================================================
    f"trade_when({NEWS_GATE_AND}, ts_decay_linear(rank(snt_value), 5), -1)",

    # =================================================================
    # Tier 8 — Different sentiment field inside the gate
    # =================================================================
    f"trade_when({NEWS_GATE_AND}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(snt_buzz), 5), -1)",
    f"trade_when({NEWS_GATE_AND}, ts_decay_linear(rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(scl12_sentiment), 5), -1)",
]
