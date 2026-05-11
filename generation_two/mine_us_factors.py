"""US-stock factor mining pipeline (Stage 1: pre-screen).

Pipeline contract (per the user's brief):
    1. Pull from a curated, *non-RP* alpha pool — these expressions deliberately
       avoid WQ Brain's stock recipe / starter templates. They use multi-field
       interactions, less-common fields (sentiment, options, FX, news, ratings),
       and unusual lookback constants so they don't collide with the platform's
       built-in alpha library.
    2. Backtest each candidate on the official IS window 2019-01-01..2023-12-31.
    3. Apply the hard gate:
              IS Sharpe > 1.25  AND  IS Turnover < 0.25
       Anything that fails either gate is discarded.
    4. Keep WorldQuant Brain's concurrent simulation slots saturated (this
       account = 3 slots). The pipeline maintains a sliding window of N in-flight
       simulations and refills as soon as one returns.
    5. Survivors are written to ``screening_survivors.json`` so Stage 2
       (``bayesian_tune.py``) can pick them up for hyper-parameter search.

Run::

    python -m generation_two.mine_us_factors             # default pool, slots=3
    python -m generation_two.mine_us_factors --slots 3 --limit 40
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import asdict, dataclass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation_two.core.credential_manager import CredentialManager
from generation_two.core.simulator_tester import (
    SimulationResult,
    SimulationSettings,
    SimulatorTester,
)


IS_START = "2019-01-01"
IS_END = "2023-12-31"
MIN_SHARPE = 1.25
MAX_TURNOVER = 0.25
MIN_FITNESS = 1.0


# ---------------------------------------------------------------------------
# Novel candidate pool — deliberately not WQ Brain's RP / starter templates.
# Characteristics:
#   * mostly multi-field interactions (not single-field reductions)
#   * non-standard lookbacks (89, 144, 233 — Fibonacci) where useful
#   * uncommon fields: scl12_buzz, anl4_*, fn_oth_income_*, implied_volatility_*,
#     news12_*, fn_assets_fair_val_a, model risk fields
#   * conditional / regime-switching structures via trade_when / if_else
# ---------------------------------------------------------------------------
ROUND53_ALPHAS: list[str] = [
    # Round 53 — R52 on TOP1000 showed IV momentum's turnover dropped
    # from 0.352 → 0.209 (now passes turnover gate), Sharpe stable at 0.73.
    # Tune IV momentum further. Will run this against TOP500 universe.

    # 1. IV momentum 5d (faster).
    "group_neutralize(ts_decay_linear(rank(ts_delta(implied_volatility_mean_30, 5)), 60), industry)",

    # 2. IV momentum 20d (slower).
    "group_neutralize(ts_decay_linear(rank(ts_delta(implied_volatility_mean_30, 20)), 60), industry)",

    # 3. IV60 momentum 10d (different IV horizon — mid-term).
    "group_neutralize(ts_decay_linear(rank(ts_delta(implied_volatility_mean_60, 10)), 60), industry)",

    # 4. Call-IV-30 momentum (different field, different econ).
    "group_neutralize(ts_decay_linear(rank(ts_delta(implied_volatility_call_30, 10)), 60), industry)",

    # 5. Put-IV-30 momentum (downside fear flow).
    "group_neutralize(ts_decay_linear(rank(ts_delta(implied_volatility_put_30, 10)), 60), industry)",

    # 6. IV momentum FLIPPED sign (in case the right direction is short).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(implied_volatility_mean_30, 10)), 60), industry)",

    # 7. IV momentum + ROA delta combo (uncorrelated alpha streams).
    "group_neutralize(ts_decay_linear(0.5 * rank(ts_delta(implied_volatility_mean_30, 10)) + 0.5 * rank(ts_delta(return_assets, 90)), 60), industry)",

    # 8. IV momentum with subindustry neut.
    "group_neutralize(ts_decay_linear(rank(ts_delta(implied_volatility_mean_30, 10)), 60), subindustry)",
]


ROUND52_ALPHAS: list[str] = [
    # Round 52 — switch universe to USA TOP1000. The strongest raw signals
    # from prior rounds on TOP3000 hit a ~0.89 ceiling. TOP1000 has less
    # micro-cap noise and tighter group structure, so we test if the same
    # signals lift over the 1.25 gate.

    # 1. ROA delta 90d (R50 winner on TOP3000: +0.83).
    "group_neutralize(ts_decay_linear(rank(ts_delta(return_assets, 90)), 60), industry)",

    # 2. PV-contrarian corr 20 (R39 winner on TOP3000: +0.89).
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_delta(volume, 1), 20)), 60), industry)",

    # 3. Dollar-volume reversal 40d (R39 winner: +0.75).
    "group_neutralize(ts_decay_linear(-rank(ts_sum(returns * vwap * volume, 40)), 60), industry)",

    # 4. Combo PV-contrarian + dollar-vol reversal (R40 combo: +0.88).
    "group_neutralize(ts_decay_linear(0.5 * -rank(ts_corr(returns, ts_delta(volume, 1), 20)) + 0.5 * -rank(ts_sum(returns * vwap * volume, 40)), 30), industry)",

    # 5. Intraday (close-open)/open reversal (R46 sign-flipped: +0.76).
    "group_neutralize(ts_decay_linear(-rank(ts_sum((close - open) / open, 20)), 60), industry)",

    # 6. IV momentum 10d (R48: +0.72, turn 0.352 was over).
    "group_neutralize(ts_decay_linear(rank(ts_delta(implied_volatility_mean_30, 10)), 60), industry)",

    # 7. Sentiment delta 5d flipped (R48: |Sharpe| 0.98 raw, turn 1.055).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(scl12_sentiment, 5)), 60), industry)",

    # 8. AR(1) autocorrelation flipped (R46: +0.42).
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_delay(returns, 1), 60)), 60), industry)",
]


ROUND51_ALPHAS: list[str] = [
    # Round 51 — R50 surfaced ROA delta 90d at Sharpe +0.83 / turn 0.036 /
    # fit 0.43 (low turn, plenty of headroom for cascade-decay or combo).
    # Tune the ROA-momentum direction.

    # 1. ROA delta 60d (faster).
    "group_neutralize(ts_decay_linear(rank(ts_delta(return_assets, 60)), 60), industry)",

    # 2. ROA delta 120d (slower).
    "group_neutralize(ts_decay_linear(rank(ts_delta(return_assets, 120)), 60), industry)",

    # 3. ROE delta 90d (sibling factor).
    "group_neutralize(ts_decay_linear(rank(ts_delta(return_equity, 90)), 60), industry)",

    # 4. ROA delta + ROE delta combo (50/50).
    "group_neutralize(ts_decay_linear(0.5 * rank(ts_delta(return_assets, 90)) + 0.5 * rank(ts_delta(return_equity, 90)), 60), industry)",

    # 5. ROA delta with SUBINDUSTRY neutralization.
    "group_neutralize(ts_decay_linear(rank(ts_delta(return_assets, 90)), 60), subindustry)",

    # 6. ROA delta with cascade-decay (boost — same trick that broke price-accel).
    "group_neutralize(ts_decay_linear(ts_decay_linear(rank(ts_delta(return_assets, 90)), 60), 60), industry)",

    # 7. ROA delta with heavier single decay 250.
    "group_neutralize(ts_decay_linear(rank(ts_delta(return_assets, 90)), 250), industry)",

    # 8. ROA acceleration (2nd-derivative of ROA, structurally different from
    #    blocked price-accel since the underlying field is a quality ratio).
    "group_neutralize(ts_decay_linear(rank(ts_delta(ts_delta(return_assets, 30), 30)), 60), industry)",
]


ROUND50_ALPHAS: list[str] = [
    # Round 50 — found canonical profitability/quality fields:
    # return_assets (ROA), return_equity (ROE), capex, retained_earnings,
    # cap, adv20, sharesout. These are textbook quality factors.

    # 1. ROA Quality (high ROA outperform).
    "group_neutralize(ts_decay_linear(rank(return_assets), 60), industry)",

    # 2. ROE Quality.
    "group_neutralize(ts_decay_linear(rank(return_equity), 60), industry)",

    # 3. Capex intensity reversal (short capex-heavy names).
    "group_neutralize(ts_decay_linear(-rank(capex / (cap + 1)), 60), industry)",

    # 4. Retained earnings momentum (book-value growth).
    "group_neutralize(ts_decay_linear(rank(ts_delta(retained_earnings, 90)), 60), industry)",

    # 5. IV term-structure curvature (convexity, NOT skew like R22-R26).
    "group_neutralize(ts_decay_linear(rank((implied_volatility_mean_120 + implied_volatility_mean_60) - 2 * implied_volatility_mean_90), 60), industry)",

    # 6. ADV20 surge (recent dollar-volume growth normalized).
    "group_neutralize(ts_decay_linear(rank(ts_delta(adv20, 60) / (adv20 + 1)), 60), industry)",

    # 7. Cap-weighted earnings yield.
    "group_neutralize(ts_decay_linear(rank(anl4_adjusted_netincome_ft / cap), 60), industry)",

    # 8. ROA delta (improving profitability).
    "group_neutralize(ts_decay_linear(rank(ts_delta(return_assets, 90)), 60), industry)",
]


ROUND49_ALPHAS: list[str] = [
    # Round 49 — R48 surfaced 3 promising alt-data raw signals:
    #   scl12_sentiment 5d delta (flipped): |Sharpe| 0.98 / turn 1.055 (crazy)
    #   IV-mean-30 10d momentum:           Sharpe 0.72 / turn 0.352 (over)
    #   CFPS / close yield:                Sharpe 0.60 / turn 0.012 (stable)
    # Apply cascade-decay smoothing trick to cut the high-turn signals.
    # Also add a few brand-new alt-data architectures.

    # 1. Cascade-decay sentiment delta flipped (smooth the 1.055-turn beast).
    "group_neutralize(ts_decay_linear(ts_decay_linear(-rank(ts_delta(scl12_sentiment, 5)), 60), 60), industry)",

    # 2. Cascade-decay IV momentum (pull 0.352 turn under 0.25).
    "group_neutralize(ts_decay_linear(ts_decay_linear(rank(ts_delta(implied_volatility_mean_30, 10)), 60), 60), industry)",

    # 3. Combine CFPS yield + IV momentum (potentially uncorrelated).
    "group_neutralize(ts_decay_linear(0.5 * rank(anl4_af_cfps_value / close) + 0.5 * rank(ts_delta(implied_volatility_mean_30, 10)), 60), industry)",

    # 4. Single-decay sentiment delta flipped with HEAVY decay 250.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(scl12_sentiment, 5)), 250), industry)",

    # 5. NEW: realized 3rd moment (manual skewness via cubed returns).
    "group_neutralize(ts_decay_linear(-rank(ts_mean(returns * returns * returns, 60)), 60), industry)",

    # 6. NEW: industry-residual returns accumulated (peer-adjusted momentum).
    "group_neutralize(ts_decay_linear(rank(ts_sum(returns - group_mean(returns, 1, industry), 20)), 60), industry)",

    # 7. NEW: dividend-yield proxy (using analyst dividend forecast).
    "group_neutralize(ts_decay_linear(rank(anl4_af_div_value / close), 60), industry)",

    # 8. NEW: news12 sentiment if available — try a probe.
    "group_neutralize(ts_decay_linear(rank(nws12_afterhsz_01l), 60), industry)",
]


ROUND48_ALPHAS: list[str] = [
    # Round 48 — R47 sim-failed on guessed field names (eps_estimate_value,
    # actual_eps_value_quarterly, dividend_estimate_value). Switch to the
    # canonical field IDs found in upstream_data_fields_USA_TOP3000.json:
    # anl4_af_eps_value (actual EPS), anl4_afv4_eps_mean (forecast mean),
    # anl4_afv4_eps_std (forecast dispersion), scl12_sentiment,
    # implied_volatility_mean_30, anl4_adjusted_netincome_ft (proven).

    # 1. EPS estimate revision momentum (analyst forecast mean delta).
    "group_neutralize(ts_decay_linear(rank(ts_delta(anl4_afv4_eps_mean, 30)), 60), industry)",

    # 2. EPS forecast dispersion (analyst disagreement, contrarian on certainty).
    "group_neutralize(ts_decay_linear(-rank(anl4_afv4_eps_std / (abs(anl4_afv4_eps_mean) + 0.01)), 60), industry)",

    # 3. Earnings surprise (actual EPS minus forecast mean).
    "group_neutralize(ts_decay_linear(rank(anl4_af_eps_value - anl4_afv4_eps_mean), 60), industry)",

    # 4. Sentiment LEVEL (not buzz — distinct from R23).
    "group_neutralize(ts_decay_linear(rank(scl12_sentiment), 60), industry)",

    # 5. Sentiment momentum (5d delta).
    "group_neutralize(ts_decay_linear(rank(ts_delta(scl12_sentiment, 5)), 60), industry)",

    # 6. Short-IV momentum (delta of implied vol — different from put-call skew).
    "group_neutralize(ts_decay_linear(rank(ts_delta(implied_volatility_mean_30, 10)), 60), industry)",

    # 7. Cap-adjusted earnings momentum (proven anl4_adjusted_netincome_ft).
    "group_neutralize(ts_decay_linear(rank(ts_delta(anl4_adjusted_netincome_ft, 60) / cap), 60), industry)",

    # 8. CFPS-yield (operating cash-flow per share / price).
    "group_neutralize(ts_decay_linear(rank(anl4_af_cfps_value / close), 60), industry)",
]


ROUND47_ALPHAS: list[str] = [
    # Round 47 — alternative-data fields (analyst, fundamentals,
    # sentiment, options term-structure, news). Field names taken from
    # the upstream USA TOP3000 schema. AVOID R22-R26 IV-skew family
    # (those used put_30 - call_30, the "skew"); this round uses
    # term-structure (long-IV minus short-IV) instead.

    # 1. EPS estimate revision momentum (30d delta of consensus EPS estimate).
    "group_neutralize(ts_decay_linear(rank(ts_delta(eps_estimate_value, 30)), 60), industry)",

    # 2. Sentiment momentum (daily change in social sentiment).
    "group_neutralize(ts_decay_linear(rank(scl12_sentiment_fast_d1), 60), industry)",

    # 3. Earnings surprise (actual minus consensus estimate).
    "group_neutralize(ts_decay_linear(rank(actual_eps_value_quarterly - eps_estimate_value), 60), industry)",

    # 4. IV TERM-STRUCTURE (long-IV minus short-IV, different from R22-R26
    #    which was put-call SKEW). Long IV term-structure = contango.
    "group_neutralize(ts_decay_linear(rank(implied_volatility_mean_360 - implied_volatility_mean_30), 60), industry)",

    # 5. Sales surprise (quarterly actual vs median estimate).
    "group_neutralize(ts_decay_linear(rank(actual_sales_value_quarterly - median_sales_estimate), 60), industry)",

    # 6. Cash-flow quality (CFPS over EPS, quarterly).
    "group_neutralize(ts_decay_linear(rank(actual_cashflow_per_share_value_quarterly / (actual_eps_value_quarterly + 0.001)), 60), industry)",

    # 7. Dividend estimate momentum (rising dividend expectations).
    "group_neutralize(ts_decay_linear(rank(ts_delta(dividend_estimate_value, 60)), 60), industry)",

    # 8. Sentiment buzz delta (R23 used raw scl12_buzz; this is the daily
    #    delta, different structural signal).
    "group_neutralize(ts_decay_linear(rank(ts_delta(scl12_buzz, 5)), 60), industry)",
]


ROUND46_ALPHAS: list[str] = [
    # Round 46 — R45 all 8 failed. Try truly different angles:
    # time-series structure, autocorrelation, cross-frequency divergence,
    # intraday-shape distribution. Avoid: returns-rev, IV-skew, BAB,
    # PV-contrarian, dollar-vol-rev, price-acceleration.

    # 1. Returns AR(1) autocorrelation (persistence/anti-persistence).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_delay(returns, 1), 60)), 60), industry)",

    # 2. Volume variability (coefficient of variation of volume).
    "group_neutralize(ts_decay_linear(rank(ts_std_dev(volume, 20) / (ts_mean(volume, 20) + 1)), 60), industry)",

    # 3. Intraday upper-tail skewness: (high-close)/(close-low) ratio.
    "group_neutralize(ts_decay_linear(rank((high - close) / (close - low + 0.001)), 60), industry)",

    # 4. MACD-like short MA minus long MA divergence (short=12, long=26).
    "group_neutralize(ts_decay_linear(rank(ts_mean(close, 12) - ts_mean(close, 26)), 60), industry)",

    # 5. Cross-frequency momentum divergence (10d minus 60d return).
    "group_neutralize(ts_decay_linear(rank(ts_mean(returns, 10) - ts_mean(returns, 60)), 60), industry)",

    # 6. Negative-side AR(1) (anti-persistence detector).
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_delay(returns, 1), 60)), 60), industry)",

    # 7. Open-close intraday gap accumulated (different from R45#3
    #    overnight component — this is OPEN→CLOSE only).
    "group_neutralize(ts_decay_linear(rank(ts_sum((close - open) / open, 20)), 60), industry)",

    # 8. High-Low spread expansion (vol expansion regime).
    "group_neutralize(ts_decay_linear(rank(ts_delta(high - low, 20)), 60), industry)",
]


ROUND45_ALPHAS: list[str] = [
    # Round 45 — price-acceleration family ALSO collinear with user's
    # existing factor library. Need brand-new architectures.
    # Blocked: returns-rev, IV-skew, BAB, PV-contrarian, dollar-vol-rev,
    # price-acceleration.

    # 1. 52-week-high drawdown reversion (long depressed names).
    "group_neutralize(ts_decay_linear(rank((close / ts_max(close, 252)) - 1), 60), industry)",

    # 2. Short-vs-long volatility regime ratio (short rising-vol names).
    "group_neutralize(ts_decay_linear(-rank(ts_std_dev(returns, 10) / (ts_std_dev(returns, 60) + 0.001)), 60), industry)",

    # 3. Intraday-only return accumulation (long persistent intraday buyers).
    "group_neutralize(ts_decay_linear(rank(ts_sum((close - open) / ts_delay(close, 1), 20)), 60), industry)",

    # 4. Daily range as % of price (low-range names tend to outperform).
    "group_neutralize(ts_decay_linear(-rank(ts_mean((high - low) / close, 20)), 60), industry)",

    # 5. Max single-day return reversal (short tail-risk names).
    "group_neutralize(ts_decay_linear(-rank(ts_max(returns, 20)), 60), industry)",

    # 6. Signed days count (count of positive vs negative days).
    "group_neutralize(ts_decay_linear(rank(ts_sum(sign(returns), 20)), 60), industry)",

    # 7. Range-position in 60-day window (where close sits in recent range).
    "group_neutralize(ts_decay_linear(rank((close - ts_min(low, 60)) / (ts_max(high, 60) - ts_min(low, 60) + 0.001)), 60), industry)",

    # 8. Min single-day return (long stocks with worst recent days).
    "group_neutralize(ts_decay_linear(-rank(ts_min(returns, 20)), 60), industry)",
]


ROUND44_ALPHAS: list[str] = [
    # Round 44 — cascade-decay trick (decay-of-decay) cut R42's
    # price-accel turnover from 0.266 → 0.100 while keeping Sharpe 1.53.
    # Apply the same trick to OTHER viable signals (R39/R40 had:
    # PV-contrarian 0.89, dollar-vol-rev 0.75, OBV-flipped 0.62) to get
    # 4 more structurally distinct survivors.

    # 1. Cascade-decay PV-contrarian (R39 winner).
    "group_neutralize(ts_decay_linear(ts_decay_linear(-rank(ts_corr(returns, ts_delta(volume, 1), 20)), 60), 60), industry)",

    # 2. Cascade-decay dollar-volume reversal (R39 winner).
    "group_neutralize(ts_decay_linear(ts_decay_linear(-rank(ts_sum(returns * vwap * volume, 40)), 60), 60), industry)",

    # 3. Cascade-decay OBV-flipped (R41 result).
    "group_neutralize(ts_decay_linear(ts_decay_linear(-rank(ts_sum(sign(returns) * volume, 20)), 60), 60), industry)",

    # 4. Cascade-decay overnight-gap momentum (R39 #5 was +0.46).
    "group_neutralize(ts_decay_linear(ts_decay_linear(rank(ts_sum(open / ts_delay(close, 1) - 1, 10)), 60), 60), industry)",

    # 5. Cascade-decay price-accel SUBINDUSTRY (variant of R43 winner).
    "group_neutralize(ts_decay_linear(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 60), 60), subindustry)",

    # 6. Cascade-decay price-accel applied to RETURNS (not close).
    "group_neutralize(ts_decay_linear(ts_decay_linear(-rank(ts_delta(ts_delta(returns, 5), 5)), 60), 60), industry)",

    # 7. Cascade-decay combo (PV-contrarian + dollar-vol-rev).
    "group_neutralize(ts_decay_linear(ts_decay_linear(0.5 * -rank(ts_corr(returns, ts_delta(volume, 1), 20)) + 0.5 * -rank(ts_sum(returns * vwap * volume, 40)), 60), 60), industry)",

    # 8. Cascade-decay price-accel with wider inner window (10/5).
    "group_neutralize(ts_decay_linear(ts_decay_linear(-rank(ts_delta(ts_delta(close, 10), 5)), 60), 60), industry)",
]


ROUND43_ALPHAS: list[str] = [
    # Round 43 — push R42 winners' turnover below 0.25 gate.
    # R42 best: -rank(ts_delta(ts_delta(close, 5), 5)) decay 250 industry
    #   Sharpe 1.77, fitness 1.38, turnover 0.266 (barely over)
    # R42 subindustry: same with decay 120, subindustry
    #   Sharpe 1.70, fitness 1.11, turnover 0.291
    # Need turn < 0.25. Try more decay or smoothing inside.

    # 1. Decay 300 industry.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 300), industry)",

    # 2. Decay 400 industry.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 400), industry)",

    # 3. Decay 200 industry + inner smoothing (ts_mean wrap close).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(ts_mean(close, 3), 5), 5)), 200), industry)",

    # 4. Decay 250 sector.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 250), sector)",

    # 5. Decay 250 market (broadest).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 250), market)",

    # 6. Decay 200 subindustry (R42#8 had decay 120 / 0.291 turn → bigger decay).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 200), subindustry)",

    # 7. Decay 250 subindustry.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 250), subindustry)",

    # 8. Double decay (cascade smoothing): decay then decay.
    "group_neutralize(ts_decay_linear(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 60), 60), industry)",
]


ROUND42_ALPHAS: list[str] = [
    # Round 42 — BREAKTHROUGH from R41: price-acceleration family
    # ts_delta(ts_delta(close, 5), 5) with WRONG sign gave |Sharpe| 1.50
    # but turnover 0.331 (over 0.25 gate). Flip sign + heavy decay smoothing
    # should land Sharpe ≥1.25 / turn <0.25.

    # 1. Flipped price-accel decay 60.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 60), industry)",

    # 2. Decay 120 (heavier smoothing to cut turnover from 0.331).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 120), industry)",

    # 3. Decay 180.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 180), industry)",

    # 4. Decay 250 (max smoothing).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 250), industry)",

    # 5. Wider inner window (10/5 instead of 5/5).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 10), 5)), 60), industry)",

    # 6. Wider outer window (5/10).
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 10)), 60), industry)",

    # 7. Applied to returns instead of close.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(returns, 5), 5)), 60), industry)",

    # 8. With subindustry neutralization, decay 120.
    "group_neutralize(ts_decay_linear(-rank(ts_delta(ts_delta(close, 5), 5)), 120), subindustry)",
]


ROUND41_ALPHAS: list[str] = [
    # Round 41 — R38-R40 plateau at Sharpe ~0.88-0.89 across PV/volume
    # variants. Try 3 boost mechanisms + 3 brand-new families to break out.

    # 1. Best combo (R40#6) with SUBINDUSTRY neutralization (finer slicing).
    "group_neutralize(ts_decay_linear(0.5 * -rank(ts_corr(returns, ts_delta(volume, 1), 20)) + 0.5 * -rank(ts_sum(returns * vwap * volume, 40)), 30), subindustry)",

    # 2. Best combo with SECTOR (broader; more cross-sector active).
    "group_neutralize(ts_decay_linear(0.5 * -rank(ts_corr(returns, ts_delta(volume, 1), 20)) + 0.5 * -rank(ts_sum(returns * vwap * volume, 40)), 30), sector)",

    # 3. Best combo with TRADE_WHEN filter (only trade on high-volume regime).
    #    Filter: ts_mean(volume, 5) > ts_mean(volume, 60).
    "group_neutralize(ts_decay_linear(trade_when(ts_mean(volume, 5) > ts_mean(volume, 60), 0.5 * -rank(ts_corr(returns, ts_delta(volume, 1), 20)) + 0.5 * -rank(ts_sum(returns * vwap * volume, 40)), -1), 30), industry)",

    # 4. Best combo with group_rank (rank within industry) instead of plain rank.
    "group_neutralize(ts_decay_linear(0.5 * -group_rank(ts_corr(returns, ts_delta(volume, 1), 20), industry) + 0.5 * -group_rank(ts_sum(returns * vwap * volume, 40), industry), 30), industry)",

    # 5. NEW: price acceleration (2nd-derivative of close — short-window
    #    inflection points).
    "group_neutralize(ts_decay_linear(rank(ts_delta(ts_delta(close, 5), 5)), 60), industry)",

    # 6. NEW: coefficient of variation reversal (short high CV = high noise).
    "group_neutralize(ts_decay_linear(-rank(ts_std_dev(returns, 20) / (abs(ts_mean(returns, 20)) + 0.001)), 60), industry)",

    # 7. NEW: range-relative price z-score (z-score breakout reversion).
    "group_neutralize(ts_decay_linear(-rank((close - ts_mean(close, 60)) / (ts_std_dev(close, 60) + 0.001)), 60), industry)",

    # 8. NEW: OBV momentum FLIPPED (R40 raw was -0.62, flip = +0.62).
    "group_neutralize(ts_decay_linear(-rank(ts_sum(sign(returns) * volume, 20)), 60), industry)",
]


ROUND40_ALPHAS: list[str] = [
    # Round 40 — push R39's two viable signals over the 1.25 gate.
    #   Price-Volume contrarian (corr 20): Sharpe 0.89, turn 0.059
    #   Dollar-volume reversal (sum 40):    Sharpe 0.75, turn 0.045
    # Both have very low turnover → room to drop decay for more responsiveness.
    # Add 2 brand-new families: intraday body/range pressure & on-balance volume.

    # 1. PV-contrarian corr 20, decay 20 (sharper).
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_delta(volume, 1), 20)), 20), industry)",

    # 2. PV-contrarian corr 20, decay 30.
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_delta(volume, 1), 20)), 30), industry)",

    # 3. PV-contrarian corr 10, decay 30 (shorter corr window).
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_delta(volume, 1), 10)), 30), industry)",

    # 4. Dollar-volume reversal sum 20, decay 30.
    "group_neutralize(ts_decay_linear(-rank(ts_sum(returns * vwap * volume, 20)), 30), industry)",

    # 5. Dollar-volume reversal sum 60, decay 60.
    "group_neutralize(ts_decay_linear(-rank(ts_sum(returns * vwap * volume, 60)), 60), industry)",

    # 6. COMBO: PV-contrarian + dollar-vol reversal (both contrarian-flow).
    "group_neutralize(ts_decay_linear(0.5 * -rank(ts_corr(returns, ts_delta(volume, 1), 20)) + 0.5 * -rank(ts_sum(returns * vwap * volume, 40)), 30), industry)",

    # 7. NEW: intraday body/range pressure momentum.
    #    (close-open)/(high-low) is the "candlestick body proportion";
    #    accumulated body pressure should predict continuation.
    "group_neutralize(ts_decay_linear(rank(ts_sum((close - open) / (high - low + 0.0001), 20)), 60), industry)",

    # 8. NEW: on-balance volume momentum (sign(returns) * volume).
    "group_neutralize(ts_decay_linear(rank(ts_sum(sign(returns) * volume, 20)), 60), industry)",
]


ROUND39_ALPHAS: list[str] = [
    # Round 39 — R38 revealed 3 of 5 families had viable absolute Sharpe
    # (0.46, 0.78, 0.89) but WRONG sign. Flip signs and sweep windows
    # to push |Sharpe| over the 1.25 gate. Also fix Williams %R (sim-failed
    # at 0/0/0 likely because the raw signal had no rank dispersion;
    # wrap in rank() to force cross-sectional ranking).

    # 1. Price-Volume contrarian: short stocks where return tracks volume
    #    surges (high-conviction-up = overdone), long where return is
    #    independent of volume. R38 raw: Sharpe -0.89 → flip to +0.89.
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_delta(volume, 1), 20)), 60), industry)",

    # 2. Price-Volume contrarian, longer corr window.
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_delta(volume, 1), 40)), 60), industry)",

    # 3. Dollar-volume reversal: short heavy net buy-flow names (R38: -0.78
    #    → flip to +0.78).
    "group_neutralize(ts_decay_linear(-rank(ts_sum(returns * vwap * volume, 20)), 60), industry)",

    # 4. Dollar-volume reversal, longer accumulation window.
    "group_neutralize(ts_decay_linear(-rank(ts_sum(returns * vwap * volume, 40)), 60), industry)",

    # 5. Overnight-gap momentum (flip of R38#1: long gappers, not reversion).
    "group_neutralize(ts_decay_linear(rank(ts_sum(open / ts_delay(close, 1) - 1, 10)), 60), industry)",

    # 6. Overnight-gap momentum, 20d accumulation.
    "group_neutralize(ts_decay_linear(rank(ts_sum(open / ts_delay(close, 1) - 1, 20)), 60), industry)",

    # 7. Williams %R FIXED: wrapped in rank(), positive sign (long high
    #    range-position = breakout momentum).
    "group_neutralize(ts_decay_linear(rank((close - ts_min(low, 30)) / (ts_max(high, 30) - ts_min(low, 30))), 60), industry)",

    # 8. Williams %R FIXED, negative sign (short range-top = mean-reversion),
    #    with rank wrap.
    "group_neutralize(ts_decay_linear(-rank((close - ts_min(low, 30)) / (ts_max(high, 30) - ts_min(low, 30))), 60), industry)",
]


ROUND38_ALPHAS: list[str] = [
    # Round 38 — CLEAN SLATE. R37 exposed the BAB family (R27-R36) as
    # numerical-noise signal: ts_mean(returns, 1) === returns, so the
    # "correlation with self" rank() collapsed to a constant and only
    # produced trades from accidental floating-point ties in late 2022-2023.
    # Replacing with a real market proxy (group_mean(returns,1,market))
    # gave Sharpe ~0.4-0.6, confirming there was no genuine alpha.
    #
    # Five brand-new architectures, each structurally and economically
    # different from prior winners (R1-R20 returns-reversal, R22-R26 IV-skew,
    # R27-R37 BAB-degenerate). Pure PV fields only — no field-name risk.
    # All wrap in group_neutralize(ts_decay_linear(..., 60), industry).

    # 1. Price-Volume confirmation (long stocks where returns track volume
    #    surges = breakout-quality momentum, short low-conviction moves).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_delta(volume, 1), 20)), 60), industry)",

    # 2. Overnight-gap reversion (short stocks that gap up overnight,
    #    long stocks that gap down — overnight-gap-reversal anomaly).
    "group_neutralize(ts_decay_linear(-rank(ts_sum(open / ts_delay(close, 1) - 1, 10)), 60), industry)",

    # 3. Williams %R mean-reversion (short stocks at top of 30-day range,
    #    long stocks at bottom — short-horizon range reversion).
    "group_neutralize(ts_decay_linear(-((close - ts_min(low, 30)) / (ts_max(high, 30) - ts_min(low, 30))), 60), industry)",

    # 4. Dollar-volume momentum (long stocks with positive dollar-volume
    #    flow over 20 days; structurally different from price-only momentum).
    "group_neutralize(ts_decay_linear(rank(ts_sum(returns * vwap * volume, 20)), 60), industry)",

    # 5. Low-vol anomaly (short high-realized-vol names, long low-vol;
    #    classic Black-Frazzini-Pedersen low-vol premium, but NOT BAB
    #    because uses realized-vol of stock returns directly, no market
    #    correlation involved).
    "group_neutralize(ts_decay_linear(-rank(ts_std_dev(returns, 60)), 60), industry)",
]


ROUND37_ALPHAS: list[str] = [
    # Round 37 — STRUCTURAL FIX. Yearly stats on platform showed
    # group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns,1),
    # 120)), 60), industry) had Sharpe=0 / turn=0 / 0 longs/0 shorts for
    # 2019-2022 inclusive. Root cause: ts_mean(returns, 1) is just `returns`
    # itself (rolling 1-day mean), so ts_corr(returns, returns, N) is ~1.0 and
    # rank() collapses to a constant until numerical noise breaks the tie in
    # late 2022. The whole BAB family was structurally degenerate — IS Sharpe
    # was being earned over <1.5 of the 5 IS years.
    #
    # Real fix: correlate against group_mean(returns, 1, market) (equal-weighted
    # market return) — an actual cross-sectional series that varies every day
    # from t=120 onward. This is the canonical Frazzini-Pedersen BAB shape.

    # 1. Pure corrected-BAB-flipped corr 60, decay 60.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, group_mean(returns, 1, market), 60)), 60), industry)",

    # 2. Pure corrected-BAB-flipped corr 30, decay 60.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, group_mean(returns, 1, market), 30)), 60), industry)",

    # 3. Pure corrected-BAB-flipped corr 90, decay 60.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, group_mean(returns, 1, market), 90)), 60), industry)",

    # 4. Pure corrected-BAB-flipped corr 120, decay 60.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, group_mean(returns, 1, market), 120)), 60), industry)",

    # 5. Corrected-BAB corr 60 against sector-average instead of market.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, group_mean(returns, 1, sector), 60)), 60), industry)",

    # 6. Corrected BAB 0.9 + VWAP-rev 0.1 decay 90 (replacement for #6 with
    #    proper market proxy).
    "group_neutralize(ts_decay_linear(0.9 * rank(ts_corr(returns, group_mean(returns, 1, market), 60)) + 0.1 * -ts_rank(close - vwap, 252), 90), industry)",
]


ROUND36_ALPHAS: list[str] = [
    # Round 36 — push factor #6 sub-univ Sharpe over 0.66 cutoff (currently
    # 0.64 with R33's 0.8 BAB + 0.2 VWAP-rev decay 90). Need MORE BAB.
    # R35#1 showed BAB 0.9 + VWAP 0.1 decay 60 hits Sharpe 1.68 but turn 0.253.
    # Heavier decay should bring turnover under gate.

    # 1. BAB 0.9 + VWAP-rev 0.1 decay 90 (heavier decay to cut turnover).
    "group_neutralize(ts_decay_linear(0.9 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.1 * -ts_rank(close - vwap, 252), 90), industry)",

    # 2. BAB 0.85 + VWAP-rev 0.15 decay 90 (middle ground).
    "group_neutralize(ts_decay_linear(0.85 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.15 * -ts_rank(close - vwap, 252), 90), industry)",

    # 3. BAB 0.9 + VWAP-rev 0.1 decay 120 (slowest).
    "group_neutralize(ts_decay_linear(0.9 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.1 * -ts_rank(close - vwap, 252), 120), industry)",

    # 4. BAB 0.95 + VWAP-rev 0.05 decay 90 (near-pure BAB but small VWAP filler).
    "group_neutralize(ts_decay_linear(0.95 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.05 * -ts_rank(close - vwap, 252), 90), industry)",
]


ROUND35_ALPHAS: list[str] = [
    # Round 35 — fix #1-3 book size with minimal aux. Keep BAB dominant
    # so IS Sharpe/fit metrics match pure BAB (1.36 / 0.055 / 1.64) while
    # adding small universal-coverage component to fill 2020-2022 book gap.

    # 1. BAB 0.9 + VWAP-rev 0.1 (minimal microstructure aux).
    "group_neutralize(ts_decay_linear(0.9 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.1 * -ts_rank(close - vwap, 252), 60), industry)",

    # 2. BAB 0.95 + tiny cap-rank coverage filler.
    "group_neutralize(ts_decay_linear(0.95 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.05 * rank(cap), 60), industry)",

    # 3. BAB 0.9 + rank(volume) coverage filler.
    "group_neutralize(ts_decay_linear(0.9 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.1 * rank(volume), 60), industry)",

    # 4. BAB 0.9 + small reversal (returns rank, full coverage).
    "group_neutralize(ts_decay_linear(0.9 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.1 * -ts_rank(returns, 60), 60), industry)",
]


ROUND34_ALPHAS: list[str] = [
    # Round 34 — fix factors #1-3 (pure BAB-flipped) book utilization
    # which is < 50% during 2020-2022. The `rank(ts_corr)` signal is
    # sparse in volatile periods. Add normalization/dispersion wrappers
    # to expand book without losing the BAB edge.

    # 1. scale() wrap — forces |long|+|short| = 1 per side, all positions
    #    participate proportionally.
    "group_neutralize(ts_decay_linear(scale(rank(ts_corr(returns, ts_mean(returns, 1), 60))), 60), industry)",

    # 2. BAB + small returns-reversal coverage filler (BAB 0.8 + reversal 0.2).
    #    The returns reversal has 100% coverage and fills in book.
    "group_neutralize(ts_decay_linear(0.8 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.2 * -ts_rank(returns, 252), 60), industry)",

    # 3. BAB + small cap-rank coverage filler.
    "group_neutralize(ts_decay_linear(0.8 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.2 * rank(cap), 60), industry)",

    # 4. BAB ts_zscore wrap (z-score against own 252d history) — converts
    #    static rank to dispersed values, more book participation.
    "group_neutralize(ts_decay_linear(rank(ts_zscore(ts_corr(returns, ts_mean(returns, 1), 60), 252)), 60), industry)",
]


ROUND33_ALPHAS: list[str] = [
    # Round 33 — fix sub-universe Sharpe for combo factor #6.
    # Current #6 = 0.5 BAB + 0.5 VWAP-rev decay 90: sub-univ Sharpe 0.61 < 0.65.
    # VWAP-rev is large-cap-specific; BAB is more universal. Lean on BAB.

    # 1. BAB-heavy 0.7 + VWAP-rev 0.3 decay 120.
    "group_neutralize(ts_decay_linear(0.7 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.3 * -ts_rank(close - vwap, 252), 120), industry)",

    # 2. BAB-heavy 0.8 + VWAP-rev 0.2 decay 90.
    "group_neutralize(ts_decay_linear(0.8 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.2 * -ts_rank(close - vwap, 252), 90), industry)",

    # 3. BAB + low-vol (lower-vol works in all universes).
    "group_neutralize(ts_decay_linear(0.5 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.5 * -rank(ts_std_dev(returns, 252)), 60), industry)",

    # 4. BAB-heavy + low-vol (lean on universal signals).
    "group_neutralize(ts_decay_linear(0.7 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.3 * -rank(ts_std_dev(returns, 252)), 60), industry)",
]


ROUND32_ALPHAS: list[str] = [
    # Round 32 — push HIGH-BETA × VWAP-rev combos under turnover gate.
    # R31#3 mult, R31#4 add(0.5/0.5) were both 1.68/0.253/1.11 — turnover
    # 0.003 over gate. Heavier decay or different weights should fix it.
    # Need 1 more PASS to reach 5 this iteration.

    # 1. HIGH-BETA × VWAP-rev mult, decay 90.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 60)) * -ts_rank(close - vwap, 252), 90), industry)",

    # 2. HIGH-BETA + VWAP-rev additive (0.5/0.5), decay 90.
    "group_neutralize(ts_decay_linear(0.5 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.5 * -ts_rank(close - vwap, 252), 90), industry)",

    # 3. HIGH-BETA + VWAP-rev additive (0.7/0.3 favor BAB), decay 60.
    "group_neutralize(ts_decay_linear(0.7 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.3 * -ts_rank(close - vwap, 252), 60), industry)",

    # 4. HIGH-BETA + VWAP-rev additive (0.3/0.7 favor VWAP), decay 60.
    "group_neutralize(ts_decay_linear(0.3 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.7 * -ts_rank(close - vwap, 252), 60), industry)",
]


ROUND31_ALPHAS: list[str] = [
    # Round 31 — extend HIGH-BETA winner with settings/structure diversity.
    # 3 PASSes so far this iteration; need 2 more.

    # 1. HIGH-BETA + sector neut.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 60)), 60), sector)",

    # 2. HIGH-BETA + decay 30 (faster).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 60)), 30), industry)",

    # 3. HIGH-BETA × VWAP-rev multiplicative (combine 2 effects).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 60)) * -ts_rank(close - vwap, 252), 60), industry)",

    # 4. HIGH-BETA + VWAP-rev additive composite.
    "group_neutralize(ts_decay_linear(0.5 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.5 * -ts_rank(close - vwap, 252), 60), industry)",

    # 5. Pure ts_corr (no rank wrapper) — different normalization.
    "group_neutralize(ts_decay_linear(ts_corr(returns, ts_mean(returns, 1), 60), 60), industry)",

    # 6. HIGH-BETA + corr window 120 (longer).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 120)), 60), industry)",
]


ROUND30_ALPHAS: list[str] = [
    # Round 30 — boost fitness for VWAP-rev (Sharpe great, fit < 1.0).
    # Plus more HIGH-BETA variants. Session has 1 PASS so far (R29#1
    # BAB-flipped); need 4 more.

    # 1. VWAP-rev cross-sectional rank only (no ts_rank compression).
    "group_neutralize(ts_decay_linear(-rank(close - vwap), 60), industry)",

    # 2. VWAP-rev with signed_power 1.5 amplification.
    "group_neutralize(ts_decay_linear(signed_power(-ts_rank(close - vwap, 252) + 0.5, 1.5), 60), industry)",

    # 3. VWAP-rev raw scaled (no rank, full magnitude).
    "group_neutralize(ts_decay_linear(-(close - vwap) / (vwap + 1), 60), industry)",

    # 4. HIGH-BETA with decay 90 (R29#1 was decay 60, PASS).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 60)), 90), industry)",

    # 5. HIGH-BETA with corr window 90d (R29#1 used 60d).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 90)), 60), industry)",

    # 6. HIGH-BETA with corr window 30d (faster).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 30)), 60), industry)",
]


ROUND29_ALPHAS: list[str] = [
    # Round 29 — variants of 2 close-to-passing R27/R28 architectures.
    # R27#5 VWAP-rev: Sharpe 1.50 / turn 0.224 / fit 0.98 (fit just below 1.0)
    # R28#5 BAB flipped: Sharpe -1.36 / fit -1.64 → flipped = +1.36 / +1.64 PASS
    # Both use FULL-coverage signals (returns, close, vwap) → meet weight
    # concentration cap. Variations on decay, neut group, lookback.

    # 1. HIGH-BETA LONG — R28#5 BAB with sign flipped. NEW logic.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 60)), 60), industry)",

    # 2. HIGH-BETA LONG with subindustry neut (different group).
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 60)), 60), subindustry)",

    # 3. HIGH-BETA LONG with decay 120.
    "group_neutralize(ts_decay_linear(rank(ts_corr(returns, ts_mean(returns, 1), 60)), 120), industry)",

    # 4. VWAP-REV with decay 90 (R27#5 was decay 60).
    "group_neutralize(ts_decay_linear(-ts_rank(close - vwap, 252), 90), industry)",

    # 5. VWAP-REV with subindustry neut.
    "group_neutralize(ts_decay_linear(-ts_rank(close - vwap, 252), 60), subindustry)",

    # 6. VWAP-REV with decay 120.
    "group_neutralize(ts_decay_linear(-ts_rank(close - vwap, 252), 120), industry)",
]


ROUND28_ALPHAS: list[str] = [
    # Round 28 — distinct from R1-R26 winners AND satisfies new constraints:
    #   weight_concentration <= 10%, sub_universe_sharpe >= 0.79.
    # Strategy: use FULL-COVERAGE signals (returns/close/volume/vwap have
    # data for all stocks; IV-skew only had data for ~half, causing
    # concentrated weights). Lower sim-level truncation to 0.05.

    # 1. TREND-FOLLOWING — 50d/200d SMA ratio. Long stocks in uptrend.
    "group_neutralize(ts_decay_linear(rank(ts_mean(close, 50) / (ts_mean(close, 200) + 0.01) - 1), 60), industry)",

    # 2. LOW-VOL ANOMALY — 252d realized vol, long low-vol. Smoothed + neut.
    "group_neutralize(ts_decay_linear(-rank(ts_std_dev(returns, 252)), 60), industry)",

    # 3. DOLLAR-VOLUME momentum — long high dollar-volume names.
    "group_neutralize(ts_decay_linear(rank(volume * vwap), 60), industry)",

    # 4. VOL-OF-VOL — higher-moment vol-dispersion signal.
    "group_neutralize(ts_decay_linear(rank(ts_std_dev(ts_std_dev(returns, 21), 60)), 60), industry)",

    # 5. BETTING-AGAINST-BETA — corr of stock vs cross-sectional mean.
    "group_neutralize(ts_decay_linear(-rank(ts_corr(returns, ts_mean(returns, 1), 60)), 60), industry)",

    # 6. LOTTERY AVERSION — long stocks with LOW max-daily-return (avoid lottery).
    "group_neutralize(ts_decay_linear(-rank(ts_max(returns, 21)), 60), industry)",
]


ROUND27_ALPHAS: list[str] = [
    # Round 27 — 5 (+1) candidates with structure AND logic distinct from
    # ALL prior winners.
    # Prior winners:
    #   R1-R20: returns mean-reversion (ts_rank/ts_zscore of returns +
    #           ts_decay_linear + subindustry/sector/industry neut)
    #   R22-R26: IV-skew (put_30 - call_30) inverse + smoothing + neut
    # Round 27 explores DIFFERENT signals: long-term momentum, skewness
    # premium, range vol premium, intraday gap, VWAP reversion, overnight gap.

    # 1. LONG-TERM MOMENTUM — long winners over 252d. NOT reversal.
    #    No outer smoothing or neutralization (rely on sim-level industry).
    "rank(ts_sum(returns, 252))",

    # 2. SKEWNESS PREMIUM — long high-skew stocks (lottery effect).
    "group_neutralize(ts_decay_linear(rank(ts_skewness(returns, 60)), 60), industry)",

    # 3. RANGE VOL PREMIUM — 60d high-low range, ts_mean smoother.
    #    Different smoother (ts_mean) than R1-R26 (ts_decay_linear).
    "group_neutralize(ts_mean(rank(ts_max(high, 60) - ts_min(low, 60)), 60), industry)",

    # 4. INTRADAY-GAP MOMENTUM — 21d sum of close-open gap.
    "group_neutralize(-ts_decay_linear(rank(ts_sum(close - open, 21)), 60), industry)",

    # 5. VWAP REVERSION — temporal rank (ts_rank) of close-vwap. Different
    #    operator (ts_rank temporal) than R1-R20 (rank cross-sectional).
    "group_neutralize(ts_decay_linear(-ts_rank(close - vwap, 252), 60), industry)",

    # 6. OVERNIGHT GAP REVERSAL — open vs prior close. Subindustry neut,
    #    decay 90 (different settings).
    "group_neutralize(ts_decay_linear(-rank(open - ts_delay(close, 1)), 90), subindustry)",
]


ROUND26_ALPHAS: list[str] = [
    # Round 26 — 4 PASS so far this user-request (all IV-skew variants).
    # Try for category diversity in the 5th factor.

    # 1. IV skew decay 240 — slowest variant, fallback if buzz fails.
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30), 240), industry)",

    # 2. SENTIMENT: scl12_buzz with heavy decay 120 (R23#4 had decay 60 turn 0.46;
    #    decay 120 should cut turnover roughly in half).
    "group_neutralize(ts_decay_linear(-rank(scl12_buzz), 120), industry)",

    # 3. Cross-category additive — IV skew + buzz (both anti-predictive).
    "group_neutralize(ts_decay_linear(-0.7 * rank(implied_volatility_put_30 - implied_volatility_call_30) - 0.3 * rank(scl12_buzz), 60), industry)",

    # 4. SENTIMENT polarity — scl12_sent if it exists.
    "group_neutralize(ts_decay_linear(-rank(scl12_sent), 60), industry)",
]


ROUND25_ALPHAS: list[str] = [
    # Round 25 — 5 more IV-skew variants for diversity. Need 2 PASS.

    # 1. IV skew + decay 30 (faster smoothing).
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30), 30), industry)",

    # 2. IV skew + decay 90.
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30), 90), industry)",

    # 3. IV skew × cap rank (multiplicative size weighting) — different STRUCTURE.
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30) * rank(cap), 60), industry)",

    # 4. IV skew + decay 180 (slow).
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30), 180), industry)",

    # 5. IV skew TS-RANK (temporal not cross-sectional) — different OPERATOR.
    "group_neutralize(ts_decay_linear(-ts_rank(implied_volatility_put_30 - implied_volatility_call_30, 60), 60), industry)",
]


ROUND24_ALPHAS: list[str] = [
    # Round 24 — exploit R22#1 winner (IV skew + industry neut, Sharpe 2.10)
    # by varying neutralization group, decay window, and adding cross-category
    # interactions. R23 confirmed individual IV legs lack edge — skew is key.

    # 1. IV skew + SECTOR neut (different group from R22#1's industry).
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30), 60), sector)",

    # 2. IV skew + SUBINDUSTRY neut (third group choice).
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30), 60), subindustry)",

    # 3. IV skew + LONGER DECAY 120 (slow-moving signal).
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30), 120), industry)",

    # 4. IV midpoint (call+put)/2 — vol level (NOT skew). Long high-IV
    #    stocks (vol-risk premium harvest).
    "group_neutralize(ts_decay_linear(-rank((implied_volatility_call_30 + implied_volatility_put_30) / 2), 60), industry)",

    # 5. RELATIVE VOLUME shock — pure liquidity signal (NOT IV-based,
    #    NOT reversal). Long stocks with current volume above 60d mean.
    "group_neutralize(ts_decay_linear(rank(volume / (ts_mean(volume, 60) + 1)), 60), industry)",
]


ROUND23_ALPHAS: list[str] = [
    # Round 23 — build on R22 IV-skew win (Sharpe 2.10).
    # IV-skew is anti-predictive (high put-skew = oversold). Extend to:
    # - ratio formulation (vs difference)
    # - put IV alone, call IV alone
    # - sentiment without intraday-sign noise
    # - intraday range vol-premium (different category)

    # 1. IV skew RATIO — different formulation than R22#1 difference.
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 / (implied_volatility_call_30 + 0.01)), 60), industry)",

    # 2. PUT IV alone — long stocks with low put IV (less hedging demand).
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30), 60), industry)",

    # 3. CALL IV alone — long stocks with low call IV (no chasing).
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_call_30), 60), industry)",

    # 4. SENTIMENT buzz alone (no intraday sign — fix R22#2 turnover).
    "group_neutralize(ts_decay_linear(-rank(scl12_buzz), 60), industry)",

    # 5. INTRADAY range vol-premium — long high-range stocks.
    "group_neutralize(ts_decay_linear(rank((high - low) / (close + 0.01)), 60), industry)",
]


ROUND22_ALPHAS: list[str] = [
    # Round 22 — fix R21 fails + add diverse new candidates.
    # R21 findings: IV skew & sentiment buzz are STRONG signals but
    # anti-predictive (flip sign needed) AND need smoothing. Field names
    # matter: anl4_eps_mean, implied_volatility_call_120,
    # operating_income/sales (no smoothing) all sim-failed.
    # Stick to proven-existing fields.

    # 1. OPTION (R21#1 fixed) — IV skew, flipped + smoothed + neutralized.
    "group_neutralize(ts_decay_linear(-rank(implied_volatility_put_30 - implied_volatility_call_30), 60), industry)",

    # 2. SENTIMENT (R21#3 fixed) — buzz × intraday, flipped + smoothed.
    "group_neutralize(ts_decay_linear(-rank(ts_zscore(scl12_buzz, 60)) * sign(close - open), 60), industry)",

    # 3. OPTION × VOLUME (cross-category interaction) — long stocks with
    #    high call IV AND high volume (event-anticipation).
    "group_neutralize(ts_decay_linear(rank(implied_volatility_call_30) * rank(volume), 60), industry)",

    # 4. SENTIMENT acceleration — buzz 5d delta. Event-driven momentum.
    "group_neutralize(ts_decay_linear(rank(ts_delta(scl12_buzz, 5)), 60), industry)",

    # 5. MICROSTRUCTURE — VWAP-close gap as informed-flow indicator.
    #    Long stocks where VWAP > close (institutional buying).
    "group_neutralize(ts_decay_linear(rank((vwap - close) / (close + 0.01)), 60), industry)",
]


ROUND21_ALPHAS: list[str] = [
    # Round 21 — STRUCTURE + LOGIC both distinct from R1-R20.
    # All R1-R20 used `returns` as input + ts_decay_linear smoothing +
    # subindustry group_neutralize, with mean-reversion logic.
    # Round 21 pivots to NON-returns inputs (Option, Analyst, Sentiment,
    # Fundamental) and NON-reversal logic (event-driven, quality, vol-premium).

    # 1. OPTION — Put-Call IV skew (defensive-demand premium). Pure
    #    cross-sectional rank, no time-series smoothing, no group_neutralize
    #    (rely on sim-level INDUSTRY neut). Long stocks with high put skew.
    "rank(implied_volatility_put_30 - implied_volatility_call_30)",

    # 2. ANALYST — EPS-revision momentum (event-driven, NOT reversal). 21d
    #    delta of mean analyst EPS forecast, ranked, ts_decay_linear=30.
    #    No outer group_neutralize.
    "ts_decay_linear(rank(ts_delta(anl4_eps_mean, 21)), 30)",

    # 3. SENTIMENT — Buzz-shock × intraday direction. Cross-sectional
    #    sentiment-buzz z-score multiplied by close-vs-open sign. SECTOR
    #    neutralization (different group than R1-R20).
    "group_neutralize(rank(ts_zscore(scl12_buzz, 60)) * sign(close - open), sector)",

    # 4. OPTION — IV term structure. Short-dated vs long-dated call IV
    #    ratio, ranked. Long stocks with elevated short-term IV (forward
    #    risk premium). INDUSTRY neutralization.
    "group_neutralize(rank(implied_volatility_call_30 / (implied_volatility_call_120 + 0.01)), industry)",

    # 5. FUNDAMENTAL — Operating-margin quality. Pure cross-sectional
    #    rank of operating_income / sales (NOT reversal). INDUSTRY neut.
    "group_neutralize(rank(operating_income / (sales + 1)), industry)",
]


ROUND20_ALPHAS: list[str] = [
    # Round 20 — 3 small, high-confidence variants. Need 1 more PASS.
    # Both extreme-decile (90/10) and quartile (75/25) barbells PASS — 80/20
    # is in between and should also PASS. Adds 2 more for buffer.

    # 1. F5 barbell 80/20 — between PASSing 75/25 (R18#4) and 90/10 (R18#5).
    "group_neutralize(ts_decay_linear(if_else(ts_rank(returns, 252) > 0.8, -1, if_else(ts_rank(returns, 252) < 0.2, 1, 0)), 60), subindustry)",

    # 2. F4 additive with equal weights (0.5r + 0.5z).
    "group_neutralize(ts_decay_linear(-0.5 * ts_rank(returns, 252) - 0.5 * ts_zscore(returns, 252), 60), subindustry)",

    # 3. F1 with lookback 200 (between PASSing 144 and 252).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 200), 60), subindustry)",
]


ROUND19_ALPHAS: list[str] = [
    # Round 19 — retry R18 fails + 3 new variants. Need 2 more PASSes.

    # 1. Retry: F1 with market neutralization (R18#2 submit-failed).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252), 60), market)",

    # 2. Retry: F4 additive re-weighted 0.7r + 0.3z (R18#6 submit-failed).
    "group_neutralize(ts_decay_linear(-0.7 * ts_rank(returns, 252) - 0.3 * ts_zscore(returns, 252), 60), subindustry)",

    # 3. Retry: F1 lookback=180 (R18#3 sim-failed).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 180), 60), subindustry)",

    # 4. F1 lookback=200 (between 180 and 252).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 200), 60), subindustry)",

    # 5. F4 additive opposite weighting (0.3 rank + 0.7 zscore).
    "group_neutralize(ts_decay_linear(-0.3 * ts_rank(returns, 252) - 0.7 * ts_zscore(returns, 252), 60), subindustry)",

    # 6. F5 barbell 80/20 (between quartile and decile).
    "group_neutralize(ts_decay_linear(if_else(ts_rank(returns, 252) > 0.8, -1, if_else(ts_rank(returns, 252) < 0.2, 1, 0)), 60), subindustry)",
]


ROUND18_ALPHAS: list[str] = [
    # Round 18 — settings/parameter variations of existing winners.
    # User: "all settings tunable; just hit Sharpe>1.25, turn<0.25, fit>1.0".
    # Existing winners' inner neutralization is subindustry. Vary group,
    # lookback, threshold, additive weights to produce new factor IDs that
    # still inherit the proven reversal architecture.

    # 1. F1 with sector neutralization (broader group than subindustry).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252), 60), sector)",

    # 2. F1 with market neutralization (broadest grouping).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252), 60), market)",

    # 3. F1 with intermediate lookback 180 (between 144 and 252).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 180), 60), subindustry)",

    # 4. F5 (barbell) with quartile threshold (75/25 not 85/15).
    "group_neutralize(ts_decay_linear(if_else(ts_rank(returns, 252) > 0.75, -1, if_else(ts_rank(returns, 252) < 0.25, 1, 0)), 60), subindustry)",

    # 5. F5 (barbell) with extreme decile (90/10) — fewer but stronger signals.
    "group_neutralize(ts_decay_linear(if_else(ts_rank(returns, 252) > 0.9, -1, if_else(ts_rank(returns, 252) < 0.1, 1, 0)), 60), subindustry)",

    # 6. F4 additive with re-weighted components (0.7 rank + 0.3 zscore).
    "group_neutralize(ts_decay_linear(-0.7 * ts_rank(returns, 252) - 0.3 * ts_zscore(returns, 252), 60), subindustry)",
]


ROUND17_ALPHAS: list[str] = [
    # Round 17 — tame reversal-acceleration turnover.
    # Baseline (R13#1/R16#6): -ts_delta(ts_rank(returns, 252), 5) decay 60
    #   TOP3000: Sharpe 1.77 / turn 0.640 / fit 0.86
    #   TOP1000: Sharpe 1.78 / turn 0.640 / fit 0.96  ← fit just below 1.0 gate
    # Need turn <0.25 without crushing Sharpe (R14#1 decay=200 over-killed it
    # to 0.59 / 0.45). Try ALTERNATIVE turnover-shaping transforms.

    # 1. Hump-filter 0.05 — suppress small wiggles in the change rate.
    "group_neutralize(ts_decay_linear(hump(-ts_delta(ts_rank(returns, 252), 5), 0.05), 60), subindustry)",

    # 2. Hump-filter 0.10 — more aggressive deadband.
    "group_neutralize(ts_decay_linear(hump(-ts_delta(ts_rank(returns, 252), 5), 0.10), 60), subindustry)",

    # 3. Vol-scaled — divide acceleration by realized vol (slow-moving denom).
    "group_neutralize(ts_decay_linear(-ts_delta(ts_rank(returns, 252), 5) / (ts_std_dev(returns, 21) + 0.01), 60), subindustry)",

    # 4. Longer interval (delta=21) — measure rank change over 21d not 5d.
    "group_neutralize(ts_decay_linear(-ts_delta(ts_rank(returns, 252), 21), 60), subindustry)",

    # 5. Pre-smoothed ranks — ts_mean the rank series before differencing.
    "group_neutralize(ts_decay_linear(-ts_delta(ts_mean(ts_rank(returns, 252), 21), 5), 60), subindustry)",

    # 6. TS-zscore of the delta — standardize cross-sectionally before decay
    #    (60d window matches the existing winning decay).
    "group_neutralize(ts_decay_linear(-ts_zscore(ts_delta(ts_rank(returns, 252), 5), 60), 60), subindustry)",
]


ROUND16_ALPHAS: list[str] = [
    # Round 16 — re-screen the best non-template candidates from Rounds
    # 13-15 on a DIFFERENT universe (USA TOP1000 or TOP500). The TOP3000
    # ceiling for non-template architectures was Sharpe ~1.02 / fitness
    # ~0.79. Liquidity-tier filtering may admit different signal shapes.

    # Top non-template performers from R13-R15:
    "group_neutralize(ts_decay_linear(-rank(ts_zscore(ts_sum(returns, 21), 60)), 60), subindustry)",      # R15#3
    "group_neutralize(ts_decay_linear(if_else(volume > 2 * ts_mean(volume, 21), -ts_rank(returns, 252), 0), 60), subindustry)",  # R15#5
    "group_neutralize(ts_decay_linear(if_else(ts_std_dev(returns, 21) > ts_std_dev(returns, 252), -ts_zscore(returns, 252), 0), 60), subindustry)",  # R15#1
    "group_neutralize(ts_decay_linear(if_else(ts_std_dev(returns, 21) > ts_std_dev(returns, 252), -ts_rank(returns, 252), 0), 60), subindustry)",  # R13#6
    "group_neutralize(ts_decay_linear(-rank(ts_sum(returns, 5) + ts_sum(returns, 21) + ts_sum(returns, 63)), 60), subindustry)",  # R14#5
    "group_neutralize(ts_decay_linear(-ts_delta(ts_rank(returns, 252), 5), 60), subindustry)",            # R13#1
]


ROUND15_ALPHAS: list[str] = [
    # Round 15 — Rounds 13/14 produced 0 survivors. New attempts focus on
    # gating/conditional architectures that use existing winning *inner*
    # signals but novel *outer* selection logic, plus parameter sweeps.

    # 1. Vol-ratio regime gating × zscore inner (improves R13#6 which had
    #    rank inner Sharpe 0.76).
    "group_neutralize(ts_decay_linear(if_else(ts_std_dev(returns, 21) > ts_std_dev(returns, 252), -ts_zscore(returns, 252), 0), 60), subindustry)",

    # 2. Reversal-acceleration moderate (bridges R13#1 decay=60 Sharpe 1.77 turn 0.64
    #    ↔ R14#1 decay=200 Sharpe 0.59). Decay=100 + delta=10.
    "group_neutralize(ts_decay_linear(-ts_delta(ts_rank(returns, 252), 10), 100), subindustry)",

    # 3. Cross-sectional rank of TS zscore of cumulative-returns —
    #    two-stage normalization (ts_zscore inside, then rank).
    "group_neutralize(ts_decay_linear(-rank(ts_zscore(ts_sum(returns, 21), 60)), 60), subindustry)",

    # 4. Negative-skew regime gating × reversal. Simpler than R13#5
    #    (no else-branch flip — sim-fail was likely the dual-active else).
    "group_neutralize(ts_decay_linear(if_else(ts_skewness(returns, 60) < 0, -ts_rank(returns, 252), 0), 60), subindustry)",

    # 5. Volume-shock-gated reversal — trade reversal ONLY on
    #    high-volume days (volume > 2× 21d mean). Different from
    #    volume_shock template (which uses rank(ts_zscore(volume))).
    "group_neutralize(ts_decay_linear(if_else(volume > 2 * ts_mean(volume, 21), -ts_rank(returns, 252), 0), 60), subindustry)",

    # 6. Inverse-vol-weighted reversal — divide the reversal signal by
    #    realized vol. Differs from Classical mom_12_1_volscaled (which
    #    vol-scales price momentum) — here it's the rank reversal.
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252) / (ts_std_dev(returns, 21) + 0.01), 60), subindustry)",
]


ROUND14_ALPHAS: list[str] = [
    # Round 14 — Round 13 gave 0 survivors. Fixes + new architectures
    # structurally distinct from Alpha-101 / Classical templates AND
    # the 5 existing PASSing factors.

    # 1. Reversal acceleration with heavy decay (R13#1 was Sharpe 1.77 /
    #    turn 0.64; push decay 60→200 + interval 5→10 to slash turnover).
    "group_neutralize(ts_decay_linear(-ts_delta(ts_rank(returns, 252), 10), 200), subindustry)",

    # 2. Multi-horizon zscore spread, sign-flipped (R13#2 was -0.81 / turn 0.099).
    "group_neutralize(ts_decay_linear(ts_zscore(returns, 252) - ts_zscore(returns, 60), 60), subindustry)",

    # 3. Drawdown signal as raw DIFFERENCE (no division — R13#4 had ratio
    #    which sim-failed). Stocks deep in drawdown get long-weight.
    "group_neutralize(ts_decay_linear(ts_rank(close - ts_max(close, 60), 252), 60), subindustry)",

    # 4. Trend-regime-gated reversal (replaces skewness gate which sim-failed).
    #    Only trade reversal when stock is BELOW its 252d-mean (oversold regime).
    "group_neutralize(ts_decay_linear(if_else(close < ts_mean(close, 252), -ts_rank(returns, 252), 0), 60), subindustry)",

    # 5. Multi-scale cumulative-return reversal — cross-sectional rank of
    #    sum-of-cumulative-returns across 3 horizons. Templates use
    #    single-horizon cumulative reversal; multi-scale composition is new.
    "group_neutralize(ts_decay_linear(-rank(ts_sum(returns, 5) + ts_sum(returns, 21) + ts_sum(returns, 63)), 60), subindustry)",

    # 6. Tail-event reversal with fixed threshold (replaces σ-scaled R13#3
    #    which sim-failed). Long signed-flip of large-magnitude returns only.
    "group_neutralize(ts_decay_linear(-ts_sum(if_else(abs(returns) > 0.03, returns, 0), 21), 60), subindustry)",
]


ROUND13_ALPHAS: list[str] = [
    # Round 13 — architectures explicitly NOT used in Alpha-101 or in the
    # workspace CLASSICAL_FACTORS, AND structurally distinct from the six
    # existing factor winners.
    #
    # The six existing winners all reduce to:
    #   subindustry-neutralised, decay-linear of (signed) ts_rank/ts_zscore
    #   of raw returns over 144/252d.
    # Alpha-101 patterns to avoid: ts_corr(price, volume, N), signed_power
    #   on rank-of-rank, IndNeutralize of vwap/close, ts_arg_max,
    #   ts_max/ts_min on rank composites, ts_decay_linear of rank-of-ranks.
    # Classical patterns to avoid: rev_1m/rev_1w (-ts_sum returns),
    #   vol_low_* (-ts_std_dev), idiosyncratic_vol (regression_neut),
    #   amihud, mom_12_1_volscaled (mom / ts_std_dev), return_skew_60
    #   (-ts_skewness as the signal).

    # 1. Reversal acceleration — rate of change of the ts_rank reversal
    #    signal itself. Templates use ts_delta on prices, not on rank
    #    composites. Picks stocks whose mean-reversion *signal is
    #    speeding up*, not the level.
    "group_neutralize(ts_decay_linear(-ts_delta(ts_rank(returns, 252), 5), 60), subindustry)",

    # 2. Multi-horizon zscore spread — short-minus-long ts_zscore. Picks
    #    stocks recently extreme relative to their own short history that
    #    are *not* extreme on the long horizon (transient anomaly).
    #    Templates don't compose zscore-spread across horizons.
    "group_neutralize(ts_decay_linear(-(ts_zscore(returns, 60) - ts_zscore(returns, 252)), 60), subindustry)",

    # 3. Tail-event-only reversal — only acts on |return| > 2σ days
    #    (zero otherwise). Templates have if_else on prices and ranks,
    #    but no σ-scaled return-tail filter as the only signal source.
    "group_neutralize(ts_decay_linear(ts_sum(if_else(abs(returns) > 2 * ts_std_dev(returns, 60), -returns, 0), 21), 60), subindustry)",

    # 4. Drawdown-from-rolling-peak reversal — distance from 60d high,
    #    normalised, then ranked over 252d. Templates use ts_max/ts_min
    #    inside rank composites with VWAP; this is a pure close-drawdown
    #    mean-reversion signal (long oversold stocks).
    "group_neutralize(ts_decay_linear(ts_rank((ts_max(close, 60) - close) / (ts_max(close, 60) + 0.01), 252), 60), subindustry)",

    # 5. Skew-regime-gated reversal — flips reversal sign based on
    #    rolling skewness regime. Templates use ts_skewness as a level
    #    signal (return_skew_60); here it is a regime gate.
    "group_neutralize(ts_decay_linear(if_else(ts_skewness(returns, 60) > 0, -ts_rank(returns, 252), ts_rank(returns, 252)), 60), subindustry)",

    # 6. Realized-vol-ratio regime — trade reversal ONLY when
    #    short-vol > long-vol (high-vol regime). New regime indicator
    #    not present in templates (vol_low_* uses absolute vol level).
    "group_neutralize(ts_decay_linear(if_else(ts_std_dev(returns, 21) > ts_std_dev(returns, 252), -ts_rank(returns, 252), 0), 60), subindustry)",
]


ROUND11_ALPHAS: list[str] = [
    # Round 11 — exhausted intraday/cumulative inputs. Round 11 keeps the
    # proven raw-returns input but tries four structurally-different
    # OUTER constructions:

    # 1. Additive composite — sum of two known winners (-ts_rank +
    #    -ts_zscore). Different from either alone because the signal
    #    is the linear combination.
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252) - ts_zscore(returns, 252), 60), subindustry)",

    # 2. Daily cross-sectional rank reversal — ranks stocks against each
    #    other today, then smooths. Different time dimension from
    #    -ts_rank (which is rank within a stock's own history).
    "group_neutralize(ts_decay_linear(-rank(returns), 60), subindustry)",

    # 3. Barbell extreme-decile reversal — long bottom 15 %, short top
    #    15 %, zero in the middle.
    "group_neutralize(ts_decay_linear(if_else(ts_rank(returns, 252) > 0.85, -1, if_else(ts_rank(returns, 252) < 0.15, 1, 0)), 60), subindustry)",

    # 4. Industry-level neutralization (vs subindustry) — same inner
    #    architecture, broader neutralisation grouping.
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252), 60), industry)",
]


ROUND10_ALPHAS: list[str] = [
    # Round 10 — 6 prior rounds show: PASSing alphas all use *raw daily
    # returns* as their input. Cumulative aggregations cap around 1.06.
    # Pure non-return inputs (vol, quality, sentiment) collapse under
    # subindustry neutralisation. Round 10 attempts four DIFFERENT INPUTS
    # that still have a daily-frequency reversal structure:

    # 1. Overnight return reversal — open(t) / close(t-1) mean-reverts.
    "group_neutralize(ts_decay_linear(-ts_rank((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.01), 252), 60), subindustry)",

    # 2. VWAP-close intraday flow reversal — captures end-of-day
    #    informed-flow vs daily VWAP gap.
    "group_neutralize(ts_decay_linear(-ts_rank((vwap - close) / (close + 0.01), 252), 60), subindustry)",

    # 3. Intraday range reversal — (high − low) / close as the input.
    "group_neutralize(ts_decay_linear(-ts_rank((high - low) / (close + 0.01), 252), 60), subindustry)",

    # 4. Downside-only cumulative-returns reversal — only accumulates
    #    negative-return days; high recent downside mean-reverts.
    "group_neutralize(ts_decay_linear(-ts_rank(ts_sum(if_else(returns < 0, returns, 0), 21), 252), 60), subindustry)",
]


ROUND9_ALPHAS: list[str] = [
    # Round 9 — R8-1 (cumulative-returns reversal, Sharpe 1.06 / turn 0.064)
    # nearly passed. The huge turnover budget says smoothing is too heavy.
    # Round 9 explores four genuinely distinct architectures around it.

    # 1. R8-1 with lighter decay (30 instead of 60) — should boost Sharpe.
    "group_neutralize(ts_decay_linear(-ts_rank(ts_sum(returns, 21), 252), 30), subindustry)",

    # 2. Pure low-volatility anomaly — long low-vol, short high-vol.
    #    A genuinely new family (no momentum / reversal of returns).
    "group_neutralize(ts_decay_linear(-rank(ts_std_dev(returns, 60)), 60), subindustry)",

    # 3. Cap-stratified cumulative-returns reversal (trade_when wrap on R8-1).
    "group_neutralize(trade_when(rank(cap) > 0.5, ts_decay_linear(-ts_rank(ts_sum(returns, 21), 252), 30), 0), subindustry)",

    # 4. Vol-adjusted (Sharpe-style) cumulative-returns reversal — divides
    #    the 21d cumulative return by its own 21d std-dev before ranking.
    "group_neutralize(ts_decay_linear(-ts_rank(ts_sum(returns, 21) / (ts_std_dev(returns, 21) + 0.01), 252), 60), subindustry)",
]


ROUND8_ALPHAS: list[str] = [
    # Round 8 — try four NEW architectures that haven't been the target
    # of any prior round. The hypothesis: subindustry-neutralised US
    # equities have multiple well-known anomalies beyond pure short-term
    # reversal; these test families adjacent to but distinct from the
    # known winners.

    # 1. Cumulative-returns reversal — rank the 21d cumulative return
    #    against its own 252d history, then reverse. Aggregation order
    #    is different from -ts_rank(returns, L) which ranks the raw daily
    #    returns.
    "group_neutralize(ts_decay_linear(-ts_rank(ts_sum(returns, 21), 252), 60), subindustry)",

    # 2. Industry-residual cumulative-returns reversal — first
    #    cross-sectionally z-score the 21d cumulative return within
    #    industry, then time-rank, then reverse.
    "group_neutralize(ts_decay_linear(-ts_rank(group_zscore(ts_sum(returns, 21), industry), 252), 60), subindustry)",

    # 3. 12-month total-return reversal — `close / ts_delay(close, 252)`
    #    as the reversal input. This is the classic "12m return"
    #    measurement (price ratio, no daily-return aggregation).
    "group_neutralize(ts_decay_linear(-ts_rank(close / (ts_delay(close, 252) + 0.01), 252), 60), subindustry)",

    # 4. Industry-relative LONG momentum (not reversal) — the bet flips
    #    direction. group_zscore'd 12m cumulative return within industry,
    #    smoothed.
    "group_neutralize(ts_decay_linear(group_zscore(ts_sum(returns, 252), industry), 60), subindustry)",
]


ROUND7_ALPHAS: list[str] = [
    # Round 7 — four genuinely-distinct architectures that *retain* a
    # known-strong reversal core (the only family that actually clears
    # Sharpe > 1.25 with subindustry neutralisation in this universe)
    # but combine it with structurally novel weighting / filtering.

    # 1. Reversal × inverse-volatility weighting (low-vol anomaly fused).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252) * (1 - rank(ts_std_dev(returns, 60))), 60), subindustry)",

    # 2. Reversal × value tilt (cheaper names get heavier reversal weight).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252) * rank(operating_income / cap), 60), subindustry)",

    # 3. Reversal residualised against a market-volume regime.
    #    The sign of (volume - ts_mean(volume, 252)) modulates whether the
    #    reversal applies; in low-volume regimes the signal is dampened.
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252) * trade_when(volume > ts_mean(volume, 252), 1, 0.3), 60), subindustry)",

    # 4. Reversal × FCF-yield weighting (quality-adjusted reversal).
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252) * rank(fnd6_fopo / cap), 60), subindustry)",
]


ROUND6_ALPHAS: list[str] = [
    # Round 6 — adopts the Factor Zoo (huyukun662-crypto/Factor_Zoo) workflow:
    #   Knowledge → Planner → Generator → Backtest → Evaluator
    # The Planner step demands one alpha per Factor-Zoo category. Each is
    # structurally distinct from every prior Round-3/4/5 winner.

    # ── Category 1: Price-Volume (volume-weighted, not pure returns rank) ──
    # Volume-Price Trend (VPT) smoothed long-horizon momentum.
    "group_neutralize(ts_decay_linear(rank(ts_sum(volume * returns, 60)), 40), subindustry)",

    # ── Category 2: Fundamental (book-to-price momentum, not level) ──
    # Captures companies whose B/P is *rising* over a year (cheapening).
    "group_neutralize(ts_decay_linear(ts_delta(equity / (cap + 0.01), 252), 30), subindustry)",

    # ── Category 3: Trend / Technical (Bollinger z-score, not rank) ──
    # Absolute z-score of price vs 60d mean, normalised by 60d std-dev,
    # reversal direction. Different from rank-based reversal because the
    # signal is the standardised distance rather than ordinal position.
    "group_neutralize(ts_decay_linear(-(close - ts_mean(close, 60)) / (ts_std_dev(close, 60) + 0.01), 30), subindustry)",

    # ── Category 4: Alternative (analyst-revision smoothed momentum) ──
    # Slow-burn analyst sentiment: change of a 60d-mean revision over a
    # full year, then smoothed. No price/returns input at all.
    "group_neutralize(ts_decay_linear(ts_delta(ts_mean(anl4_adjusted_netincome_ft, 60), 144), 30), subindustry)",
]


ROUND5_ALPHAS: list[str] = [
    # Round 5 — four STRUCTURALLY DIFFERENT alpha families. Round 3/4
    # converged on a single template (smoothed returns-rank reversal); the
    # user asked for genuine structural diversity.
    #   F1: time-series z-score reversal (different normalisation than
    #       rank-based; uses standard deviation rather than ordinal rank)
    #   F2: drawdown-from-high reversion (technical, no rank)
    #   F3: cross-group arbitrage (sector vs country relative returns)
    #   F4: defensive quality × low-volatility (fundamental + risk
    #       combination, no momentum at all)
    "group_neutralize(ts_decay_linear(-ts_zscore(returns, 252), 60), subindustry)",
    "group_neutralize(-ts_decay_linear((ts_max(close, 252) - close) / (ts_max(close, 252) + 0.01), 30), subindustry)",
    "group_neutralize(ts_decay_linear(group_zscore(returns, sector) - group_zscore(returns, country), 30), subindustry)",
    "group_neutralize(ts_decay_linear(rank(ebitda / cap) * (1 - rank(ts_std_dev(returns, 60))), 30), subindustry)",
]


ROUND4_ALPHAS: list[str] = [
    # Round 4 — fine-tune lookbacks of the strongest Round-3 template:
    #   group_neutralize(ts_decay_linear(-ts_rank(returns, $L1), $L2), subindustry)
    # Grid: L1 in {120, 144, 170, 200, 252, 300}, L2 in {40, 50, 60, 80}
    # = 24 combos. The Round-3 winner (L1=252, L2=60) sits in the middle.
    f"group_neutralize(ts_decay_linear(-ts_rank(returns, {L1}), {L2}), subindustry)"
    for L1 in (120, 144, 170, 200, 252, 300)
    for L2 in (40, 50, 60, 80)
]


ROUND3_ALPHAS: list[str] = [
    # Round 3 — bridge Round 2's gap (Sharpe 1.5 / turn 0.4) ↔ (Sharpe 1.0 / turn 0.08).
    # Three pillars to push turnover down while keeping Sharpe ≥ 1.25:
    #   (a) heavier ts_decay_linear windows on the strong base
    #   (b) hump() thresholding so noise wiggles don't trigger trades
    #   (c) gating by a slow-moving quality field (multiplicative)
    # The simulation settings layer (settings.decay) is *not* tuned here —
    # we explore the inner-decay knob first (more interpretable).

    # Heavier decay on returns-rank reversal (the strongest base in Round 2)
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 60), 30), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 60), 40), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 60), 60), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 144), 40), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 144), 60), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 252), 60), subindustry)",
    # Hump-thresholded reversal (suppresses small signal wiggles)
    "group_neutralize(ts_decay_linear(hump(-ts_rank(returns, 60), 0.1), 20), subindustry)",
    "group_neutralize(ts_decay_linear(hump(-ts_rank(returns, 144), 0.1), 30), subindustry)",
    "group_neutralize(hump(ts_decay_linear(-ts_rank(returns, 60), 30), 0.05), subindustry)",
    # Quality-gated reversal (slow operating-income sign × reversal)
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 60) * sign(ts_mean(operating_income, 252)), 30), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 60) * (1 + 0.5 * group_rank(operating_income / sales, subindustry)), 30), subindustry)",
    # Cap-stratified reversal — reversal only on liquid large names (less micro-noise turnover)
    "group_neutralize(trade_when(rank(cap) > 0.5, ts_decay_linear(-ts_rank(returns, 60), 30), 0), subindustry)",
    "group_neutralize(trade_when(rank(cap) > 0.5, ts_decay_linear(-ts_rank(returns, 144), 40), 0), subindustry)",
    # Different parameterisation: return rank vs sector mean
    "group_neutralize(ts_decay_linear(-(ts_rank(returns, 60) - 0.5), 40), subindustry)",
    "group_neutralize(ts_decay_linear(-group_zscore(ts_rank(returns, 60), subindustry), 30), subindustry)",
    # Composite: returns-reversal + dollar-volume reversal (both smoothed)
    "group_neutralize(ts_decay_linear(-0.7 * ts_rank(returns, 60) - 0.3 * ts_rank(volume * close, 60), 40), subindustry)",
    # Symmetric residual: returns minus its long mean (zero-mean reversal)
    "group_neutralize(ts_decay_linear(-(returns - ts_mean(returns, 60)), 30), subindustry)",
    "group_neutralize(ts_decay_linear(-(returns - ts_mean(returns, 144)), 60), subindustry)",
    # Triple-decay structure (decay applied to a smoothed input)
    "group_neutralize(ts_decay_linear(-ts_rank(ts_mean(returns, 5), 60), 30), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(ts_mean(returns, 10), 60), 30), subindustry)",
]


ROUND2_ALPHAS: list[str] = [
    # Round 2 — focused on the only known-strong base from earlier smoke test
    # (-ts_rank(close / ts_mean(close, 20), 30)) + heavy decay layers to push
    # turnover below 25 % while keeping Sharpe above 1.25. Each variant differs
    # in lookback / decay window so the search has gradient.

    # 1-4: smoothed mean-reversion with various decay windows
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 20), 30), 10), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 20), 30), 20), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 30), 60), 15), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 60), 60), 20), subindustry)",
    # 5-7: longer lookbacks, lower-frequency reversal
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 100), 60), 20), subindustry)",
    "group_neutralize(-ts_decay_linear(rank(close / ts_mean(close, 50)), 20), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_zscore(close / ts_mean(close, 60), 30), 15), subindustry)",
    # 8-10: returns-based reversal smoothed
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 60), 20), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(returns, 144), 30), subindustry)",
    "group_neutralize(-ts_decay_linear(ts_rank(ts_sum(returns, 21), 252), 30), subindustry)",
    # 11-12: combined reversal + quality (low turnover + signal)
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 30), 60) + rank(operating_income / sales), 15), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 60), 60) * sign(operating_income), 20), subindustry)",
    # 13-14: vol-skew × reversal combined and smoothed
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 20), 30) * (1 - rank(implied_volatility_call_30 / implied_volatility_call_120)), 15), subindustry)",
    "group_neutralize(ts_decay_linear(-ts_rank(close / ts_mean(close, 60), 60) + 0.3 * rank(implied_volatility_put_30 - implied_volatility_call_30), 20), subindustry)",
    # 15-16: slow Jegadeesh-Titman with smoothing
    "group_neutralize(ts_decay_linear(rank(ts_sum(returns, 252) - ts_sum(returns, 21)), 30), subindustry)",
    "group_neutralize(ts_decay_linear(rank(ts_sum(returns, 126) - ts_sum(returns, 21)), 25), subindustry)",
    # 17-18: pure smoothed momentum reversal at unusual windows
    "group_neutralize(-ts_decay_linear(ts_rank(close / ts_delay(close, 89), 144), 30), subindustry)",
    "group_neutralize(-ts_decay_linear(ts_rank(close / ts_delay(close, 144), 252), 40), subindustry)",
    # 19-20: cross-sectional rank reversal smoothed
    "group_neutralize(ts_decay_linear(-rank(close / ts_mean(close, 20)), 20), subindustry)",
    "group_neutralize(ts_decay_linear(-rank(returns - ts_mean(returns, 60)), 30), subindustry)",
]


NOVEL_ALPHAS: list[str] = [
    # Designed to avoid the structures of upstream worldquant-miner's
    # knowledge_pool (shu476891497-hash/worldquant-miner). Common upstream
    # tropes deliberately AVOIDED here:
    #   * single-field rank/zscore wraps (e.g. rank(fnd6_fopo / debt_lt))
    #   * ts_mean(<analyst_field>, 5)
    #   * ts_decay_linear((vwap - close) / close, 2)
    #   * ts_sum(close / ts_delay(close, 1) - 1, 20)
    #   * specific named recipes (FFO/debt_lt, fair-value liab inversion,
    #     scl12_buzz negation, EBITDA growth proxies)
    #
    # Distinctiveness levers:
    #   * second-order signals: ts_delta(ts_rank(...))
    #   * regression-residual style: signal − sector mean
    #   * Fibonacci lookbacks (89, 144, 233, 377) instead of {5,20,60,252}
    #   * non-linear transforms via signed_power / hump
    #   * cross-correlation operators (ts_corr) on uncommon pairs
    #   * triplet-field interactions (3+ different field categories per alpha)
    #   * long decay windows (≥10) to keep turnover low

    # 1. 2nd-order analyst-revision: change in cross-sectional rank of revisions
    "group_neutralize(ts_delta(group_rank(anl4_adjusted_netincome_ft, subindustry), 144), subindustry)",
    # 2. Quality residual: operating margin minus its sector-mean (long-window smoothing)
    "group_neutralize(ts_mean(operating_income / sales - ts_mean(operating_income / sales, 233), 89), subindustry)",
    # 3. Cap-stratified value: EBITDA yield only inside large caps
    "group_neutralize(trade_when(rank(cap) > 0.6, ts_decay_linear(rank(ebitda / cap), 20), 0), subindustry)",
    # 4. Sentiment regression residual: returns − beta×market via ts_corr proxy
    "group_neutralize(-ts_corr(returns, ts_delta(close, 1), 144), subindustry)",
    # 5. Convexity of profitability: signed_power of margin around its long mean
    "group_neutralize(signed_power(operating_income / sales - ts_mean(operating_income / sales, 377), 0.5), subindustry)",
    # 6. Stable dividend smoothing × low-leverage filter
    "group_neutralize(ts_decay_linear(rank(actual_dividend_value_quarterly) * (1 - rank(debt_lt / (equity + abs(debt_lt)))), 25), subindustry)",
    # 7. EBITDA acceleration over 144d but only when sector dispersion is low
    "group_neutralize(trade_when(group_rank(ts_std_dev(returns, 144), sector) < 0.5, ts_delta(ebitda / assets, 144), 0), subindustry)",
    # 8. Hump-thresholded analyst sales surprise (kills tiny noise)
    "group_neutralize(hump(rank(actual_sales_value_quarterly - ts_mean(actual_sales_value_quarterly, 4)), 0.05), subindustry)",
    # 9. FCF persistence: long-mean / long-std (uncommon ratio composition)
    "group_neutralize(ts_decay_linear(ts_mean(fnd6_fopo - capex, 233) / (ts_std_dev(fnd6_fopo - capex, 233) + 1), 15), subindustry)",
    # 10. Cross-section: cashflow PS vs sector — second-order normalisation
    "group_neutralize(group_zscore(ts_mean(actual_cashflow_per_share_value_quarterly, 89), sector), subindustry)",
    # 11. Convex value via signed_power on EBIT yield
    "group_neutralize(signed_power(rank(fnd2_ebitdm / (cap + debt_lt)) - 0.5, 3), subindustry)",
    # 12. Smoothed equity-quality with cubic compression (kills outliers)
    "group_neutralize(ts_decay_linear(signed_power(rank(equity / assets) - 0.5, 0.5), 20), subindustry)",
    # 13. Volume-trend residual: change in volume rank, long lookback
    "group_neutralize(-ts_delta(group_rank(volume, subindustry), 144), subindustry)",
    # 14. Sector-relative quality stability (long-mean of group rank)
    "group_neutralize(ts_mean(group_rank(operating_income / sales, sector), 144), subindustry)",
    # 15. Smoothed EBITDA-margin slope (regression-style via ts_delta of mean)
    "group_neutralize(ts_decay_linear(ts_delta(ts_mean(ebitda / sales, 144), 89), 15), subindustry)",
    # 16. Slow-moving leverage reduction signal (long delta on long mean)
    "group_neutralize(-ts_delta(ts_mean(debt_lt / (equity + abs(equity)), 89), 144), subindustry)",
    # 17. Profitability convexity within sector
    "group_neutralize(group_zscore(signed_power(rank(net_income / sales) - 0.5, 3), sector), subindustry)",
    # 18. Cashflow-weighted ranking with hump cleanup
    "group_neutralize(hump(group_rank(ts_mean(fnd6_fopo / cap, 233), subindustry), 0.05), subindustry)",
    # 19. Sector-residual capital intensity change
    "group_neutralize(ts_delta(capex / (assets + abs(assets)), 233) - group_zscore(ts_delta(capex / (assets + abs(assets)), 233), sector), subindustry)",
    # 20. Quality compounding: product of long-window margin & FCF ranks
    "group_neutralize(ts_decay_linear(rank(ts_mean(operating_income / sales, 144)) * rank(ts_mean(fnd6_fopo / cap, 144)), 20), subindustry)",
    # 21. Asset turnover trend (sales/assets long-window delta) — uncommon ratio
    "group_neutralize(ts_decay_linear(ts_delta(sales / (assets + abs(assets)), 233), 15), subindustry)",
    # 22. Sector-relative profitability spread (long horizon)
    "group_neutralize(group_rank(ebitda / sales, subindustry) - ts_delay(group_rank(ebitda / sales, subindustry), 233), subindustry)",
    # 23. Smoothed receivable-style proxy: capex/sales convexity
    "group_neutralize(-signed_power(ts_mean(capex / sales, 144) - ts_mean(capex / sales, 377), 0.5), subindustry)",
    # 24. Earnings yield change (long delta)
    "group_neutralize(ts_decay_linear(ts_delta(net_income / cap, 144), 25), subindustry)",
    # 25. Multi-window profitability composite (smoothed)
    "group_neutralize(ts_decay_linear(0.5 * rank(ts_mean(operating_income / sales, 89)) + 0.5 * rank(ts_mean(operating_income / sales, 233)), 20), subindustry)",
    # 26. Sector-mean-residual analyst sales coverage
    "group_neutralize(ts_mean(actual_sales_value_quarterly - ts_mean(actual_sales_value_quarterly, 252), 89) / (ts_std_dev(actual_sales_value_quarterly, 252) + 1), subindustry)",
    # 27. Inverse leverage stability (long-mean × long-std together)
    "group_neutralize(rank(1 / (1 + ts_std_dev(debt_lt / (equity + abs(equity)), 233))), subindustry)",
    # 28. Slow operating-cashflow trend with cubic outlier compression
    "group_neutralize(signed_power(ts_delta(fnd6_fopo / cap, 233), 0.5), subindustry)",
    # 29. Capex restraint × profitability: defensive composite
    "group_neutralize(ts_decay_linear((1 - rank(capex / cap)) * rank(operating_income / sales), 25), subindustry)",
    # 30. Long-window earnings consistency: rank of mean / rank of std (Sharpe-like)
    "group_neutralize(rank(ts_mean(net_income / cap, 233)) - rank(ts_std_dev(net_income / cap, 233)), subindustry)",
]


@dataclass
class ScreenRecord:
    expr: str
    success: bool
    sharpe: float
    fitness: float
    turnover: float
    returns: float
    error: str = ""

    def passes(self) -> bool:
        return (
            self.success
            and self.sharpe == self.sharpe  # not NaN
            and self.sharpe > MIN_SHARPE
            and self.turnover < MAX_TURNOVER
            and self.fitness > MIN_FITNESS
        )


def _settings(universe: str = "TOP3000", truncation: float = 0.05) -> SimulationSettings:
    return SimulationSettings(
        region="USA",
        universe=universe,
        neutralization="INDUSTRY",
        truncation=truncation,
        startDate=IS_START,
        endDate=IS_END,
    )


def _record(expr: str, res: SimulationResult | None) -> ScreenRecord:
    if res is None:
        return ScreenRecord(expr=expr, success=False, sharpe=0.0, fitness=0.0, turnover=0.0,
                            returns=0.0, error="no-result")
    return ScreenRecord(
        expr=expr,
        success=bool(res.success),
        sharpe=float(res.sharpe or 0.0),
        fitness=float(res.fitness or 0.0),
        turnover=float(res.turnover or 0.0),
        returns=float(res.returns or 0.0),
        error=res.error_message or "",
    )


def screen_candidates(
    candidates: list[str],
    *,
    slots: int = 3,
    submit_retry_delay: float = 4.0,
    submit_retry_max: int = 30,
    timeout_per_sim: int = 600,
    universe: str = "TOP3000",
) -> list[ScreenRecord]:
    """Submit candidates while keeping `slots` simulations in flight.

    Whenever a slot frees up, the next candidate is submitted. 429
    (CONCURRENT_SIMULATION_LIMIT_EXCEEDED) responses block via the existing
    submit_simulation back-off; once a sim returns, we immediately enqueue
    the next.
    """
    cm = CredentialManager(base_path=os.path.dirname(os.path.abspath(__file__)))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        raise RuntimeError("WQ Brain authentication failed")
    sess = cm.get_session()

    region_configs = {
        "USA": type(
            "RegionConfig",
            (),
            {"region": "USA", "universe": universe, "delay": 1},
        )()
    }
    tester = SimulatorTester(session=sess, region_configs=region_configs)

    settings = _settings(universe=universe)

    in_flight: dict[Future, str] = {}
    results: list[ScreenRecord] = []
    pending = list(candidates)

    def fill_slots():
        # Don't try to submit if no candidates left or no free slots
        while pending and len(in_flight) < slots:
            expr = pending.pop(0)
            for attempt in range(submit_retry_max):
                # The submitter uses requests.Session.post directly — if it
                # gets 429 it returns None. We back off and retry the same expr.
                # We do this OUTSIDE simulate_template_concurrent so a failed
                # submit doesn't burn a slot.
                progress_url = tester.submit_simulation(expr, "USA", settings)
                if progress_url:
                    fut = tester.executor.submit(
                        tester.monitor_simulation, progress_url, expr, "USA", settings
                    )
                    in_flight[fut] = expr
                    logging.info(
                        "🚀 [in-flight=%d/%d] submitted: %s",
                        len(in_flight), slots, expr[:90]
                    )
                    break
                time.sleep(submit_retry_delay)
            else:
                logging.error("Gave up submitting after %d attempts: %s",
                              submit_retry_max, expr[:90])
                results.append(ScreenRecord(
                    expr=expr, success=False, sharpe=0.0, fitness=0.0,
                    turnover=0.0, returns=0.0, error="submit-retry-exhausted",
                ))

    fill_slots()
    while in_flight:
        done = []
        for fut in list(in_flight.keys()):
            if fut.done():
                done.append(fut)
        if not done:
            time.sleep(2.0)
            continue
        for fut in done:
            expr = in_flight.pop(fut)
            try:
                res = fut.result(timeout=timeout_per_sim)
            except Exception as e:
                logging.warning("future error for %s: %s", expr[:60], e)
                res = None
            rec = _record(expr, res)
            tag = "PASS" if rec.passes() else "fail"
            logging.info(
                "✅ %s | sharpe=%+.3f turn=%.3f fitness=%+.3f | %s",
                tag, rec.sharpe, rec.turnover, rec.fitness, expr[:90]
            )
            results.append(rec)
        # Refill the freed slots
        fill_slots()

    return results


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--slots", type=int, default=3,
                   help="Concurrent WQ Brain simulation slots to saturate")
    p.add_argument("--pool",
                   choices=["novel", "round2", "round3", "round4", "round5", "round6", "round7", "round8", "round9", "round10", "round11", "round13", "round14", "round15", "round16", "round17", "round18", "round19", "round20", "round21", "round22", "round23", "round24", "round25", "round26", "round27", "round28", "round29", "round30", "round31", "round32", "round33", "round34", "round35", "round36", "round37", "round38", "round39", "round40", "round41", "round42", "round43", "round44", "round45", "round46", "round47", "round48", "round49", "round50", "round51", "round52", "round53"],
                   default="novel",
                   help="Which candidate pool to screen")
    p.add_argument("--limit", type=int, default=0,
                   help="Cap on candidates (0 = all)")
    p.add_argument("--out", default="screening_survivors.json",
                   help="Where to write the survivors")
    p.add_argument("--universe", default="TOP3000",
                   choices=["TOP3000", "TOP2000", "TOP1000", "TOP500", "TOP200"],
                   help="USA universe to screen against")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    pool = {
        "round53": ROUND53_ALPHAS,
        "round52": ROUND52_ALPHAS,
        "round51": ROUND51_ALPHAS,
        "round50": ROUND50_ALPHAS,
        "round49": ROUND49_ALPHAS,
        "round48": ROUND48_ALPHAS,
        "round47": ROUND47_ALPHAS,
        "round46": ROUND46_ALPHAS,
        "round45": ROUND45_ALPHAS,
        "round44": ROUND44_ALPHAS,
        "round43": ROUND43_ALPHAS,
        "round42": ROUND42_ALPHAS,
        "round41": ROUND41_ALPHAS,
        "round40": ROUND40_ALPHAS,
        "round39": ROUND39_ALPHAS,
        "round38": ROUND38_ALPHAS,
        "round37": ROUND37_ALPHAS,
        "round36": ROUND36_ALPHAS,
        "round35": ROUND35_ALPHAS,
        "round34": ROUND34_ALPHAS,
        "round33": ROUND33_ALPHAS,
        "round32": ROUND32_ALPHAS,
        "round31": ROUND31_ALPHAS,
        "round30": ROUND30_ALPHAS,
        "round29": ROUND29_ALPHAS,
        "round28": ROUND28_ALPHAS,
        "round27": ROUND27_ALPHAS,
        "round26": ROUND26_ALPHAS,
        "round25": ROUND25_ALPHAS,
        "round24": ROUND24_ALPHAS,
        "round23": ROUND23_ALPHAS,
        "round22": ROUND22_ALPHAS,
        "round21": ROUND21_ALPHAS,
        "round20": ROUND20_ALPHAS,
        "round19": ROUND19_ALPHAS,
        "round18": ROUND18_ALPHAS,
        "round17": ROUND17_ALPHAS,
        "round16": ROUND16_ALPHAS,
        "round15": ROUND15_ALPHAS,
        "round14": ROUND14_ALPHAS,
        "round13": ROUND13_ALPHAS,
        "round11": ROUND11_ALPHAS,
        "round10": ROUND10_ALPHAS,
        "round9": ROUND9_ALPHAS,
        "round8": ROUND8_ALPHAS,
        "round7": ROUND7_ALPHAS,
        "round6": ROUND6_ALPHAS,
        "round5": ROUND5_ALPHAS,
        "round4": ROUND4_ALPHAS,
        "round3": ROUND3_ALPHAS,
        "round2": ROUND2_ALPHAS,
        "novel": NOVEL_ALPHAS,
    }[args.pool]
    candidates = pool if args.limit <= 0 else pool[: args.limit]
    logging.info("Screening %d novel candidates against IS %s..%s universe=USA/%s slots=%d",
                 len(candidates), IS_START, IS_END, args.universe, args.slots)

    records = screen_candidates(candidates, slots=args.slots, universe=args.universe)

    survivors = [r for r in records if r.passes()]
    survivors.sort(key=lambda r: r.sharpe, reverse=True)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in survivors], f, ensure_ascii=False, indent=2)

    print("\n=== Stage-1 screening summary ===")
    print(f"tested      : {len(records)}")
    print(f"submit-fail : {sum(1 for r in records if r.error == 'submit-retry-exhausted')}")
    print(f"sim-fail    : {sum(1 for r in records if not r.success and r.error != 'submit-retry-exhausted')}")
    print(f"below-gate  : {sum(1 for r in records if r.success and not r.passes())}")
    print(f"survivors   : {len(survivors)}  (Sharpe>{MIN_SHARPE} AND turnover<{MAX_TURNOVER} AND fitness>{MIN_FITNESS})")
    if survivors:
        print("\nTop survivors:")
        for r in survivors[:10]:
            print(f"  Sharpe={r.sharpe:+.3f} turn={r.turnover:.3f} fitness={r.fitness:+.3f} | {r.expr}")
    print(f"\nwritten to  : {out_path}")
    print("=================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
