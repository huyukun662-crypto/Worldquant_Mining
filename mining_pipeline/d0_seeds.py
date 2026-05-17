"""Seed library of D0 (delay=0) factor templates.

Integer literals embedded in each expression become Optuna-tunable
windows via `expressions.parameterize()`. All expressions use only PV
fields (open/high/low/close/volume/vwap/returns/cap/sharesout/adv*)
which are D0-allowed on WQ Brain. No fundamentals, analyst, or model
fields appear (those are D1-only).

The 2026-05-17 D0 probe (`scripts/d0_probe.py`) confirmed
`rank(close - open)` returns Sharpe = -0.79 on TOP3000 / INDUSTRY /
decay=4 — i.e. the **reversion** direction (negative sign on momentum)
is the winning direction at D0 USA, so all directional seeds below are
written in their reversion-signed form.

Templates curated from public-evidence patterns:
- Alphas #42 and #101 (101 Formulaic Alphas, Kakushadze 2016)
- Range-position / volume-surprise / PV-correlation primitives that
  appear repeatedly in passing WQ Brain submissions on community repos.

Order matters: seeds tried first should have the highest a-priori chance
of passing all is.checks at D0.
"""

from __future__ import annotations

SEED_EXPRESSIONS: list[str] = [
    # =============================================================
    # Tier 1 — strong priors at D0 USA (intraday/overnight reversion)
    # =============================================================
    # Intraday reversion (Alpha #101 style, sign-flipped)
    "-rank((close - open) / ((high - low) + 0.001))",
    "-ts_decay_linear(rank((close - open) / ((high - low) + 0.001)), 5)",
    "-rank(ts_decay_linear((close - open) / ((high - low) + 0.001), 6))",

    # Overnight gap reversion
    "-rank((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001))",
    "-ts_decay_linear(rank((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001)), 4)",

    # Short-window close reversion
    "-rank((close - ts_mean(close, 5)) / (ts_std_dev(close, 5) + 0.001))",
    "-ts_rank((close - ts_mean(close, 5)) / (ts_std_dev(close, 5) + 0.001), 5)",
    "-ts_zscore(close, 5)",
    "-ts_zscore(returns, 5)",
    "-rank(ts_returns(close, 5))",

    # Alpha #42: vwap-close ratio (no sign flip — keep canonical form)
    "rank((vwap - close) / (vwap + close))",
    "ts_decay_linear(rank((vwap - close) / (vwap + close)), 5)",

    # Close vs vwap drift (reversion on intraday VWAP gap)
    "-ts_zscore((close - vwap) / (vwap + 0.001), 10)",
    "-rank((close - vwap) / (vwap + 0.001))",

    # =============================================================
    # Tier 2 — volume / microstructure
    # =============================================================
    "-ts_zscore(volume / (ts_mean(volume, 20) + 1), 20)",
    "-rank(ts_delta(log(volume + 1), 1))",
    "ts_decay_linear(-ts_corr(returns, ts_delta(log(volume + 1), 1), 10), 4)",
    "-ts_corr(rank(close), rank(volume), 10)",
    "rank(ts_decay_linear(-returns * volume / (ts_mean(volume, 20) + 1), 5))",

    # =============================================================
    # Tier 3 — range / volatility (reversion proxy)
    # =============================================================
    # Range position within day (already negative correlation with next-day return)
    "ts_decay_linear(rank((close - low) / ((high - low) + 0.001)), 6)",
    "rank(ts_decay_linear((close - low) / ((high - low) + 0.001), 5))",
    "-ts_zscore((high - low) / (close + 0.001), 20)",
    "-rank(ts_mean((high - low) / (close + 0.001), 10))",

    # =============================================================
    # Tier 4 — dollar-volume / size
    # =============================================================
    "-ts_rank(close * volume / (cap + 1), 10)",
    "rank(-ts_delta(close * volume / (cap + 1), 5))",
    "-ts_zscore(ts_corr(close, volume, 10), 20)",
]
