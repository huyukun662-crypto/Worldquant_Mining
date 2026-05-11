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


def _settings(universe: str = "TOP3000") -> SimulationSettings:
    return SimulationSettings(
        region="USA",
        universe=universe,
        neutralization="INDUSTRY",
        truncation=0.08,
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
                   choices=["novel", "round2", "round3", "round4", "round5", "round6", "round7", "round8", "round9", "round10", "round11", "round13", "round14", "round15", "round16", "round17"],
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
