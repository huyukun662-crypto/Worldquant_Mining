"""Pareto-front evolutionary search for a submittable D0 alpha.

Strategy
--------
1. Maintain an archive (list of `WQResult`) of every COMPLETE simulation.
2. Score each candidate scalarly:
       score = fitness + 0.5*sharpe + 0.1*(checks_passed/checks_total)
               - 5.0 * max(0, turnover - 0.25)
3. Each generation:
   - Pick top-K parents by score AND the Pareto front on
     (sharpe, fitness, -turnover, checks_passed).
   - Spawn `M` mutants per parent (mutation operators below).
   - Spawn `R` fresh random expressions.
   - Submit all to WQ, add results to archive.
   - If any candidate passes the full Submit gate, return it immediately.

Mutation operators (each fires with its own probability):
- swap_field    : replace a leaf field with another from the pool
- swap_op       : replace a ts_* op with another of same arity
- swap_window   : ± 1 step in WINDOWS
- swap_wrap     : replace outer cs wrap
- flip_sign     : prepend `multiply(-1, ...)`
- swap_setting  : perturb one entry in the current setting dict
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import List, Tuple

from .d0_fields import flat_rare

# ---- D0 hard constraints (per user spec 2026-05-18) -----------------------
# delay=0; SH>=2.0; FIT>=1.3; PV ∪ rare fields; decay 1-5; truncation 0.005-0.02.
PV_FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns",
             "cap", "adv20", "sharesout")

# Cached rare-field pool (loaded lazily, MATRIX-type only, alphaCount<=200).
_FIELDS_CACHE: List[str] = []

TS_OPS_1ARG = (
    "ts_mean", "ts_std_dev", "ts_zscore", "ts_rank", "ts_delta",
    "ts_decay_linear", "ts_arg_max", "ts_arg_min", "ts_quantile",
    "ts_av_diff", "ts_scale", "ts_product",
    # new (2026-05-21): unexplored time-series ops
    "ts_max", "ts_min", "jump_decay", "last_diff_value", "ts_backfill",
)
TS_OPS_2ARG = ("ts_corr", "ts_covariance")
CS_WRAPS = ("rank", "zscore", "winsorize", "normalize", "quantile", "scale",
            "group_zscore_si", "group_scale_si", "scale_down")  # group_* take subindustry
UNARY = ("hump", "signed_power", "abs", "sign", "sqrt", "inverse", "reverse")
WINDOWS = (3, 5, 10, 20, 30, 60, 120)

SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000", "TOP500"],
    "delay":          [0],
    "decay":          [1, 2, 3, 4, 5],
    "truncation":     [0.005, 0.01, 0.015, 0.02],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR"],
    "pasteurization": ["ON"],
}

SHARPE_FLOOR = 2.0
FITNESS_FLOOR = 1.3
TURNOVER_CEILING = 0.25

# C01-style structural seeds (PV-only, known-good D0 templates).
# `ts_decay_exp_window` is not in this account's operator catalog
# (verified against constants/upstream_operatorRAW.json); ts_decay_linear
# is used as the closest substitute.
SEED_EXPRS = (
    # C01: mean-reversion on intraday VWAP gap
    "ts_decay_linear(rank(divide(subtract(vwap, close), close)), 4)",
    "ts_decay_linear(rank(divide(subtract(vwap, close), close)), 3)",
    "ts_decay_linear(rank(divide(subtract(vwap, close), close)), 5)",
    # 1-day reversal on returns
    "rank(multiply(-1, returns))",
    "ts_decay_linear(rank(multiply(-1, returns)), 4)",
    # Short-window close mean-reversion
    "ts_decay_linear(rank(multiply(-1, ts_delta(close, 1))), 3)",
    "ts_decay_linear(rank(multiply(-1, ts_delta(close, 5))), 4)",
    # Volume-price correlation (illiquidity premium variant)
    "rank(multiply(-1, ts_corr(close, volume, 20)))",
    # VWAP - mid-price reversion
    "ts_decay_linear(rank(divide(subtract(vwap, divide(add(high, low), 2)), close)), 4)",
    # Intraday range relative to close
    "rank(divide(subtract(high, low), close))",
    # ADV-relative size momentum
    "rank(divide(volume, adv20))",
    "ts_decay_linear(rank(divide(volume, adv20)), 4)",
    # Glazar #25 (fitness 1.03): mid-price vs close mean-reversion
    "rank(subtract(divide(add(high, low), 2), close))",
    "ts_decay_linear(rank(subtract(divide(add(high, low), 2), close)), 4)",
    # Glazar #28 (fitness 0.99): VWAP decline scaled by recency-of-high
    "divide(divide(subtract(vwap, close), close), max(ts_decay_linear(rank(ts_arg_max(close, 30)), 2), 0.20))",
    # Tanay (real submission, D1 fitness 2.34, SH 2.27, TO 22.75%, PV-only):
    # Volume-Spike with Price-Dip Reversal
    "rank(multiply(divide(volume, divide(ts_sum(volume, 60), 60)), rank(divide(divide(ts_sum(close, 5), 5), close))))",
    # YHYYDS basic PV strategies (subindustry-grouped microstructure)
    "group_rank(divide(subtract(close, open), open), subindustry)",            # intraday return
    "group_rank(divide(subtract(high, low), open), subindustry)",              # H-L range
    "group_rank(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), subindustry)",  # overnight return
    "ts_corr(divide(volume, sharesout), abs(returns), 10)",                    # volume-|return| corr
    "group_rank(divide(subtract(divide(volume, sharesout), ts_mean(divide(volume, sharesout), 20)), ts_std_dev(divide(volume, sharesout), 20)), subindustry)",  # volume z-score
    "trade_when(greater(volume, ts_mean(volume, 20)), returns, -1)",           # vol-gated returns
    # ---- Rare-field structural priors (D0-relaxed pool) ----
    # v2 empirical winner: IV skew long-window mean-reversion (SH=1.03 once)
    "normalize(ts_decay_linear(implied_volatility_mean_skew_360, 20))",
    "normalize(ts_decay_linear(implied_volatility_mean_skew_180, 20))",
    "normalize(ts_decay_linear(implied_volatility_mean_skew_90, 20))",
    # IV term-structure carry
    "rank(divide(subtract(implied_volatility_mean_360, implied_volatility_mean_20), implied_volatility_mean_20))",
    # Historical vol crowding inversion
    "rank(multiply(-1, ts_delta(historical_volatility_180, 5)))",
    "rank(multiply(-1, ts_decay_linear(historical_volatility_60, 5)))",
    # News-momentum (when there's news, fade direction)
    "rank(multiply(-1, ts_mean(news_pct_30min, 20)))",
    # Analyst estimate revision direction
    "rank(ts_delta(est_eps, 60))",
    # ==== NEW DIRECTION (2026-05-20): sentiment / put-call / group / event ====
    # Social-media sentiment reversal & momentum (snt_/scl12_ barely mined)
    "rank(multiply(-1, ts_delta(scl12_sentiment, 5)))",
    "group_rank(scl12_sentiment, subindustry)",
    "rank(ts_mean(snt_social_value, 20))",
    "rank(multiply(-1, ts_corr(scl12_sentiment, returns, 20)))",
    "rank(divide(subtract(snt_social_volume, ts_mean(snt_social_volume, 20)), ts_std_dev(snt_social_volume, 20)))",
    "rank(multiply(-1, ts_delta(scl12_buzz, 5)))",
    "rank(ts_zscore(snt_buzz_ret, 20))",
    # Buzz-gated price reversal (event-conditional via trade_when)
    "trade_when(greater(scl12_buzz, ts_mean(scl12_buzz, 20)), multiply(-1, returns), -1)",
    "trade_when(greater(snt_social_volume, ts_mean(snt_social_volume, 20)), multiply(-1, ts_delta(close, 1)), -1)",
    # Put-Call IV spread (fear gauge — distinct from IV skew)
    "rank(subtract(implied_volatility_put_60, implied_volatility_call_60))",
    "rank(subtract(implied_volatility_put_180, implied_volatility_call_180))",
    "rank(multiply(-1, ts_delta(subtract(implied_volatility_put_180, implied_volatility_call_180), 5)))",
    "ts_decay_linear(rank(subtract(implied_volatility_put_360, implied_volatility_call_360)), 10)",
    # Group-neutralized PV reversal (cross-sectional structure, new angle)
    "group_neutralize(rank(multiply(-1, ts_delta(close, 5))), subindustry)",
    "group_rank(multiply(-1, ts_corr(high, volume, 20)), subindustry)",
    "group_neutralize(multiply(-1, ts_corr(high, volume, 20)), sector)",
    # Call-IV momentum vs realized vol divergence
    "rank(subtract(ts_zscore(implied_volatility_call_30, 20), ts_zscore(historical_volatility_30, 20)))",
    # Call-Put IV spread (INVERSE of put-call: gen-0 showed put-call gives
    # strong NEGATIVE SH at low TO, so call-put is the positive-SH direction)
    "ts_decay_linear(rank(subtract(implied_volatility_call_360, implied_volatility_put_360)), 10)",
    "ts_decay_linear(rank(subtract(implied_volatility_call_180, implied_volatility_put_180)), 10)",
    "rank(subtract(implied_volatility_call_180, implied_volatility_put_180))",
    "winsorize(ts_mean(subtract(implied_volatility_call_360, implied_volatility_put_360), 10), std=4)",
    "normalize(ts_decay_linear(subtract(implied_volatility_call_360, implied_volatility_put_360), 20))",
)

# Targeted grid around the SH=1.97, 6/8-check winner (2026-05-21):
#   zscore(ts_mean(IV_call_360 - IV_put_360, 10))  SUBINDUSTRY decay=4 trunc=0.02
# zscore/scale wrap + trunc>=0.02 clears CONCENTRATED_WEIGHT and
# LOW_SUB_UNIVERSE_SHARPE; only LOW_SHARPE (1.97 vs 2.0) remains. Sweep
# maturity × window × wrap to nudge SH past 2.0 while keeping 6/8.
def _callput_grid():
    out = []
    for M in (180, 270, 360, 720):
        for W in (5, 8, 10, 12, 15, 20):
            spread = f"subtract(implied_volatility_call_{M}, implied_volatility_put_{M})"
            out.append(f"zscore(ts_mean({spread}, {W}))")
            out.append(f"scale(ts_mean({spread}, {W}))")
    return tuple(out)

SEED_EXPRS = SEED_EXPRS + _callput_grid()

# ==== NEW STRUCTURES & OPERATORS (2026-05-21): unexplored ops ====
# ts_regression (residual/beta), group_zscore/group_scale, vector_neut,
# kth_element, jump_decay, ts_max/ts_min range, days_from_last_change,
# sqrt/inverse transforms, bucket. Mix of PV + proven rare fields.
NEWOPS_SEEDS = (
    # ts_regression residual: idiosyncratic move of price vs vwap / volume
    "ts_regression(close, vwap, 20, lag=0, rettype=0)",
    "ts_regression(returns, ts_delta(volume, 1), 60, lag=0, rettype=0)",
    # IV vs realized-vol regression residual (vol risk premium, rare-field)
    "ts_regression(implied_volatility_call_180, historical_volatility_180, 60, lag=0, rettype=0)",
    # group_zscore — group-relative normalization (new vs group_rank)
    "group_zscore(multiply(-1, ts_delta(close, 5)), subindustry)",
    "group_zscore(divide(volume, adv20), subindustry)",
    "group_zscore(multiply(-1, ts_corr(high, volume, 20)), subindustry)",
    "group_zscore(subtract(implied_volatility_call_180, implied_volatility_put_180), subindustry)",
    # group_scale
    "group_scale(multiply(-1, ts_delta(close, 5)), subindustry)",
    # vector_neut — neutralize signal A against signal B
    "vector_neut(rank(multiply(-1, ts_delta(close, 5))), rank(volume))",
    "vector_neut(rank(subtract(implied_volatility_call_180, implied_volatility_put_180)), rank(historical_volatility_180))",
    # range / extremes
    "rank(divide(subtract(ts_max(close, 20), close), subtract(ts_max(close, 20), ts_min(close, 20))))",
    "rank(multiply(-1, divide(subtract(close, ts_min(close, 20)), subtract(ts_max(close, 20), ts_min(close, 20)))))",
    # kth_element timing
    "rank(divide(subtract(close, kth_element(close, 10, 1)), close))",
    # jump_decay — jump-aware smoothing of returns
    "rank(multiply(-1, jump_decay(returns, 20)))",
    "group_zscore(jump_decay(subtract(implied_volatility_call_180, implied_volatility_put_180), 10), subindustry)",
    # days_from_last_change — information staleness
    "rank(multiply(-1, days_from_last_change(close)))",
    # signed sqrt momentum
    "multiply(sign(ts_delta(close, 5)), sqrt(abs(ts_delta(close, 5))))",
    # inverse low-vol premium
    "rank(inverse(ts_std_dev(returns, 20)))",
    # bucket discretization of reversal
    "group_zscore(bucket(rank(multiply(-1, ts_delta(close, 5))), range=\"0,1,0.1\"), subindustry)",
    # last_diff_value momentum
    "rank(divide(subtract(close, last_diff_value(close, 20)), close))",
    # ts_backfill on sparse IV then group_zscore (handle 70% coverage)
    "group_zscore(ts_backfill(subtract(implied_volatility_call_180, implied_volatility_put_180), 5), subindustry)",
    # reverse + decay
    "ts_decay_linear(reverse(ts_delta(close, 5)), 5)",
    # IV-RV spread (vol risk premium) group-normalized
    "group_zscore(subtract(implied_volatility_call_180, historical_volatility_180), subindustry)",
    "group_zscore(subtract(implied_volatility_mean_60, historical_volatility_60), subindustry)",
)
SEED_EXPRS = NEWOPS_SEEDS + SEED_EXPRS  # new ops FIRST so gen-0 runs them early

# ==== NEW DOMAIN (2026-05-21): value / quality / investment anomalies ====
# Fundamental ratios vs market cap (cap = full coverage). Quarterly-updating
# fundamentals -> naturally low turnover (good for D0). group_zscore over
# subindustry handles the ~0.50 coverage and clears sub-universe / weight
# checks (the wrap that worked for call-put). decay smooths the step updates.
VALUE_QUALITY_SEEDS = (
    # --- Value (yield to price / EV) ---
    "group_zscore(divide(ebit, enterprise_value), subindustry)",            # Greenblatt earnings yield
    "group_zscore(divide(ebitda, enterprise_value), subindustry)",
    "group_zscore(divide(cashflow, cap), subindustry)",                     # cashflow yield
    "group_zscore(divide(sales, cap), subindustry)",                        # sales-to-price
    "group_zscore(divide(fnd6_seq, cap), subindustry)",                     # book-to-market
    "group_zscore(divide(retained_earnings, cap), subindustry)",
    "group_zscore(divide(income, cap), subindustry)",                       # earnings yield
    # --- Quality (profitability / leverage) ---
    "group_zscore(return_assets, subindustry)",                             # ROA
    "group_zscore(divide(ebit, assets), subindustry)",                      # Greenblatt ROC
    "group_zscore(divide(income, fnd6_seq), subindustry)",                  # ROE
    "group_zscore(current_ratio, subindustry)",                             # liquidity
    "group_zscore(multiply(-1, divide(debt, fnd6_seq)), subindustry)",      # low leverage
    "group_zscore(divide(cash, assets), subindustry)",                      # cash holding
    # --- Investment / accruals (conservative = positive) ---
    "group_zscore(multiply(-1, ts_delta(assets, 60)), subindustry)",        # asset-growth anomaly
    "group_zscore(multiply(-1, divide(capex, assets)), subindustry)",       # low capex
    "group_zscore(multiply(-1, sales_growth), subindustry)",
    "group_zscore(multiply(-1, divide(capex, cashflow)), subindustry)",
    # --- Yield ---
    "group_zscore(divide(fnd6_dvc, cap), subindustry)",                     # dividend yield
    # --- decay-smoothed value (lower turnover) ---
    "group_zscore(ts_mean(divide(ebit, enterprise_value), 20), subindustry)",
    "group_zscore(ts_mean(divide(cashflow, cap), 20), subindustry)",
    "rank(divide(ebit, enterprise_value))",
    "rank(divide(fnd6_seq, cap))",
    # --- composite value+quality (magic formula) ---
    "group_zscore(add(divide(ebit, enterprise_value), divide(ebit, assets)), subindustry)",
    "group_zscore(subtract(divide(income, cap), divide(debt, fnd6_seq)), subindustry)",
)
SEED_EXPRS = VALUE_QUALITY_SEEDS + SEED_EXPRS  # value/quality FIRST this round

# ==== NEW DOMAIN (2026-05-21 #2): VECTOR fields via vec_* operators ====
# 330 VECTOR fields never touched (need vec_sum/vec_avg/vec_max/vec_min to
# collapse to MATRIX). Analyst estimate vectors anl4_*_est/_preest have
# coverage=1.00 (solves sub-universe). Social buzz vector reproduces
# Glazar #2 (vec_sum(buzzvec) -> SH 1.94 D1). News vectors nws12_* cov 0.97.
VECTOR_SEEDS = (
    # --- Analyst revision (est - preest), FULL coverage ---
    "group_zscore(subtract(vec_avg(anl4_dez1afv4_est), vec_avg(anl4_dez1afv4_preest)), subindustry)",
    "group_zscore(subtract(vec_avg(anl4_dez1qfv4_est), vec_avg(anl4_dez1qfv4_preest)), subindustry)",
    "group_zscore(subtract(vec_avg(anl4_dez1basicafv4_est), vec_avg(anl4_dez1basicafv4_preest)), subindustry)",
    "rank(subtract(vec_avg(anl4_dez1afv4_est), vec_avg(anl4_dez1afv4_preest)))",
    "ts_decay_linear(rank(subtract(vec_avg(anl4_dez1qfv4_est), vec_avg(anl4_dez1qfv4_preest))), 10)",
    # estimate level
    "group_zscore(vec_avg(anl4_dez1afv4_est), subindustry)",
    "group_zscore(vec_sum(anl4_dez1qfv4_est), subindustry)",
    # estimate dispersion (disagreement anomaly)
    "group_zscore(subtract(vec_max(anl4_dez1afv4_est), vec_min(anl4_dez1afv4_est)), subindustry)",
    "rank(multiply(-1, subtract(vec_max(anl4_dez1qfv4_est), vec_min(anl4_dez1qfv4_est))))",
    # --- Social buzz/sentiment vectors (Glazar #2) ---
    "ts_av_diff(vec_sum(scl12_buzzvec), 60)",
    "group_zscore(vec_sum(scl12_sentvec), subindustry)",
    "rank(multiply(-1, ts_delta(vec_avg(scl12_sentvec), 5)))",
    "ts_decay_linear(rank(vec_sum(scl12_buzzvec)), 10)",
    "group_zscore(vec_avg(scl12_typevec), subindustry)",
    # --- News vectors (cov 0.97) ---
    "group_zscore(vec_avg(nws12_mainz_01s), subindustry)",
    "rank(multiply(-1, ts_delta(vec_sum(nws12_mainz_01s), 5)))",
    "group_zscore(subtract(vec_max(nws12_mainz_01l), vec_min(nws12_mainz_01l)), subindustry)",
    "ts_decay_linear(rank(vec_avg(nws12_mainz_01p)), 10)",
    # combined: analyst revision smoothed
    "group_zscore(ts_mean(subtract(vec_avg(anl4_dez1afv4_est), vec_avg(anl4_dez1afv4_preest)), 20), subindustry)",
    "zscore(ts_mean(subtract(vec_avg(anl4_dez1qfv4_est), vec_avg(anl4_dez1qfv4_preest)), 20))",
)
SEED_EXPRS = VECTOR_SEEDS + SEED_EXPRS  # VECTOR domain FIRST this round

# ==== NEW DIRECTION (2026-05-22): multi-leg combos + IV term-structure ====
# Single families plateau at SH=2.36. Combine uncorrelated families
# (call-put IV momentum + fundamental value + PV reversal) for
# diversification beyond the ceiling and lower self-correlation. Plus
# never-tried IV term-structure slope (same option type across maturities)
# and skew MOMENTUM (ts_delta of the spread vs the ts_mean level).
def _cp(M): return f"subtract(implied_volatility_call_{M}, implied_volatility_put_{M})"
COMBO_TERM_SEEDS = (
    # --- Multi-leg: call-put IV momentum + fundamental value ---
    "add(zscore(ts_mean(" + _cp(180) + ", 20)), group_zscore(divide(sales, cap), subindustry))",
    "add(zscore(ts_mean(" + _cp(270) + ", 20)), group_zscore(divide(ebit, enterprise_value), subindustry))",
    "add(zscore(ts_mean(" + _cp(180) + ", 20)), group_zscore(divide(fnd6_seq, cap), subindustry))",
    # --- Multi-leg: call-put IV + PV reversal (uncorrelated) ---
    "add(zscore(ts_mean(" + _cp(180) + ", 20)), rank(multiply(-1, ts_corr(high, volume, 20))))",
    "add(zscore(ts_mean(" + _cp(270) + ", 20)), rank(multiply(-1, ts_delta(close, 5))))",
    # --- Weighted blends (2:1 IV:value) ---
    "add(multiply(2, zscore(ts_mean(" + _cp(180) + ", 20))), group_zscore(divide(sales, cap), subindustry))",
    # --- IV term-structure slope (same type across maturities) ---
    "zscore(ts_mean(subtract(implied_volatility_call_30, implied_volatility_call_360), 20))",
    "zscore(ts_mean(subtract(implied_volatility_put_30, implied_volatility_put_360), 20))",
    "group_zscore(ts_mean(subtract(implied_volatility_call_60, implied_volatility_call_720), 20), subindustry)",
    "zscore(ts_mean(divide(implied_volatility_call_30, implied_volatility_call_360), 20))",
    "zscore(ts_mean(subtract(implied_volatility_mean_30, implied_volatility_mean_360), 20))",
    # --- Skew MOMENTUM (change in spread, not level) ---
    "zscore(ts_delta(" + _cp(180) + ", 20))",
    "group_zscore(ts_delta(" + _cp(360) + ", 60), subindustry)",
    "zscore(ts_mean(ts_delta(" + _cp(180) + ", 5), 20))",
    "rank(multiply(-1, ts_delta(" + _cp(180) + ", 20)))",
    # --- IV x PV interaction ---
    "zscore(multiply(ts_mean(" + _cp(180) + ", 20), rank(volume)))",
    "group_zscore(multiply(ts_mean(" + _cp(180) + ", 20), sign(returns)), subindustry)",
    # --- Triple-leg composite ---
    "add(add(zscore(ts_mean(" + _cp(180) + ", 20)), group_zscore(divide(sales, cap), subindustry)), rank(multiply(-1, ts_corr(high, volume, 20))))",
    # --- call-put skew vs term-structure combo ---
    "add(zscore(ts_mean(" + _cp(180) + ", 20)), zscore(ts_mean(subtract(implied_volatility_call_30, implied_volatility_call_360), 20)))",
)
SEED_EXPRS = COMBO_TERM_SEEDS + SEED_EXPRS  # combos/term-structure FIRST

# ==== NEW DIRECTION (2026-05-22 #2): different operator/structure, low corr ====
# SH>=2.0 essentially only comes from the call-put IV signal, so to get a
# LOW-CORRELATION full-pass we keep that signal source but change the
# OPERATOR/transform (ts_rank, ts_regression residual, ts_zscore, bucket,
# quantile, signed_power, hump). A different transform reorders the cross
# section -> lower self-correlation with the zscore(ts_mean(...)) family.
def _cp2(M): return f"subtract(implied_volatility_call_{M}, implied_volatility_put_{M})"
DECORR_SEEDS = (
    # ts_rank — rank-based timing (nonlinear vs ts_mean)
    "group_zscore(ts_rank(" + _cp2(180) + ", 60), subindustry)",
    "group_zscore(ts_rank(" + _cp2(360) + ", 120), subindustry)",
    "zscore(ts_rank(" + _cp2(180) + ", 250))",
    "ts_decay_linear(group_zscore(ts_rank(" + _cp2(180) + ", 120), subindustry), 10)",
    # ts_zscore — time-series standardization (vs cross-sectional)
    "group_zscore(ts_zscore(" + _cp2(180) + ", 60), subindustry)",
    "rank(ts_zscore(" + _cp2(360) + ", 120))",
    # ts_regression residual — skew vs realized vol (idiosyncratic skew)
    "group_zscore(ts_regression(" + _cp2(180) + ", historical_volatility_180, 120, lag=0, rettype=0), subindustry)",
    "group_zscore(ts_regression(" + _cp2(360) + ", implied_volatility_mean_360, 120, lag=0, rettype=0), subindustry)",
    # bucket / quantile — discretized signal
    "group_zscore(bucket(rank(ts_mean(" + _cp2(180) + ", 20)), range=\"0,1,0.05\"), subindustry)",
    "quantile(ts_mean(" + _cp2(180) + ", 20), driver=\"uniform\")",
    # signed_power / hump — nonlinear transforms
    "group_zscore(signed_power(ts_mean(" + _cp2(180) + ", 20), 0.5), subindustry)",
    "group_zscore(hump(ts_mean(" + _cp2(180) + ", 20), 0.01), subindustry)",
    # ts_decay then ts_rank (double transform)
    "group_zscore(ts_rank(ts_decay_linear(" + _cp2(180) + ", 10), 60), subindustry)",
    # last_diff_value of skew (event-style)
    "group_zscore(last_diff_value(" + _cp2(180) + ", 20), subindustry)",
    # non-option idiosyncratic-returns attempts (different operator, may be low SH)
    "group_zscore(ts_regression(returns, ts_mean(returns, 20), 60, lag=0, rettype=0), subindustry)",
    "group_zscore(ts_rank(divide(sales, cap), 250), subindustry)",
)
SEED_EXPRS = DECORR_SEEDS + SEED_EXPRS  # decorrelation seeds FIRST


def fields_pool() -> List[str]:
    """PV (10) ∪ rare D0 fields (MATRIX, alphaCount<=200, ~76 ids)."""
    global _FIELDS_CACHE
    if not _FIELDS_CACHE:
        rare = flat_rare(universe="TOP3000", max_alpha_count=200, per_cat=30, seed=7)
        _FIELDS_CACHE = list(PV_FIELDS) + rare
    return _FIELDS_CACHE


# ---------- expression generation & mutation -------------------------------

def _rand_window(rng: random.Random) -> int:
    return rng.choice(WINDOWS)


def random_expr(rng: random.Random) -> str:
    fields = fields_pool()
    r = rng.random()
    if r < 0.55:
        op = rng.choice(TS_OPS_1ARG)
        return _wrap(rng, f"{op}({rng.choice(fields)}, {_rand_window(rng)})")
    if r < 0.80:
        op = rng.choice(TS_OPS_2ARG)
        a, b = rng.sample(fields, 2)
        return _wrap(rng, f"{op}({a}, {b}, {_rand_window(rng)})")
    # nested
    inner_op = rng.choice(TS_OPS_1ARG)
    outer_op = rng.choice(TS_OPS_1ARG)
    f = rng.choice(fields)
    return _wrap(rng,
                 f"{outer_op}({inner_op}({f}, {_rand_window(rng)}), {_rand_window(rng)})")


def _wrap(rng: random.Random, core: str) -> str:
    w = rng.choice(CS_WRAPS)
    if w == "winsorize":
        return f"winsorize({core}, std=4)"
    if w == "quantile":
        return f"quantile({core}, driver=\"gaussian\")"
    if w == "group_zscore_si":
        return f"group_zscore({core}, subindustry)"
    if w == "group_scale_si":
        return f"group_scale({core}, subindustry)"
    return f"{w}({core})"


# Mutation helpers --------------------------------------------------------

_FIELD_RE = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in PV_FIELDS) + r"|[a-z][a-z0-9_]{2,})\b"
)


def _swap_field(expr: str, rng: random.Random) -> str:
    fields = fields_pool()
    # Find all field-like tokens; only replace ones that ARE in our pool
    tokens = list(_FIELD_RE.finditer(expr))
    candidates = [m for m in tokens if m.group(1) in fields]
    if not candidates:
        return expr
    m = rng.choice(candidates)
    new = rng.choice(fields)
    return expr[:m.start()] + new + expr[m.end():]


def _swap_op(expr: str, rng: random.Random) -> str:
    # Replace a ts_* op of compatible arity
    for arity_pool in (TS_OPS_1ARG, TS_OPS_2ARG):
        positions = [(m.start(), m.end()) for op in arity_pool
                     for m in re.finditer(rf"\b{re.escape(op)}\b", expr)]
        if positions and rng.random() < 0.5:
            s, e = rng.choice(positions)
            new = rng.choice(arity_pool)
            return expr[:s] + new + expr[e:]
    return expr


def _swap_window(expr: str, rng: random.Random) -> str:
    # Pick a standalone integer literal and bump it ± 1 step
    matches = []
    for m in re.finditer(r"(?<![A-Za-z0-9_])(\d+)(?![A-Za-z0-9_.])", expr):
        try:
            val = int(m.group(1))
        except ValueError:
            continue
        if val in WINDOWS:
            matches.append(m)
    if not matches:
        return expr
    m = rng.choice(matches)
    val = int(m.group(1))
    idx = WINDOWS.index(val)
    new_idx = max(0, min(len(WINDOWS) - 1, idx + rng.choice((-1, 1))))
    new_val = WINDOWS[new_idx]
    return expr[:m.start()] + str(new_val) + expr[m.end():]


def _swap_wrap(expr: str, rng: random.Random) -> str:
    # Strip outermost CS_WRAPS call and replace
    for w in CS_WRAPS:
        prefix_simple = f"{w}("
        if expr.startswith(prefix_simple):
            inner = expr[len(prefix_simple):-1]
            # If wrap has trailing args (winsorize, quantile) strip them
            if w == "winsorize":
                inner = re.sub(r",\s*std=\d+\)?$", "", inner)
            elif w == "quantile":
                inner = re.sub(r",\s*driver=\"gaussian\"\)?$", "", inner)
            if inner.endswith(")"):
                inner = inner
            new = rng.choice([c for c in CS_WRAPS if c != w])
            return _wrap(rng, inner)
    return expr


def _flip_sign(expr: str, _: random.Random) -> str:
    if expr.startswith("multiply(-1, "):
        # already negated; remove
        return expr[len("multiply(-1, "):-1]
    return f"multiply(-1, {expr})"


MUTATIONS = (
    ("swap_field",   _swap_field,   0.45),
    ("swap_op",      _swap_op,      0.25),
    ("swap_window",  _swap_window,  0.20),
    ("swap_wrap",    _swap_wrap,    0.10),
    ("flip_sign",    _flip_sign,    0.15),
)


def mutate(expr: str, rng: random.Random, max_muts: int = 2) -> str:
    out = expr
    applied = 0
    for _, fn, p in MUTATIONS:
        if rng.random() < p:
            out = fn(out, rng)
            applied += 1
            if applied >= max_muts:
                break
    if out == expr:
        # forced single mutation
        _, fn, _ = rng.choice(MUTATIONS)
        out = fn(out, rng)
    return out


def mutate_settings(parent_settings: dict, rng: random.Random) -> dict:
    s = dict(parent_settings)
    # Drop fields not in our search space
    s = {k: s.get(k, SETTING_SPACE[k][0]) for k in SETTING_SPACE}
    # Perturb one or two keys
    keys = list(SETTING_SPACE.keys())
    for k in rng.sample(keys, k=rng.randint(1, 2)):
        s[k] = rng.choice(SETTING_SPACE[k])
    s["delay"] = 0   # fixed D0
    s["pasteurization"] = "ON"
    return s


def random_settings(rng: random.Random) -> dict:
    return {k: rng.choice(v) for k, v in SETTING_SPACE.items()}


# ---------- Pareto + scoring -----------------------------------------------

@dataclass
class Cand:
    expression: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 1.0
    fitness: float = -10.0
    checks_passed: int = 0
    checks_total: int = 0
    alpha_id: str = ""
    ok: bool = False
    error: str = ""

    @property
    def check_ratio(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 0.0

    @property
    def score(self) -> float:
        if not self.ok:
            return -100.0
        return (self.fitness
                + 0.5 * self.sharpe
                + 0.1 * self.check_ratio
                - 5.0 * max(0.0, self.turnover - 0.25))

    @property
    def passes_submit_gate(self) -> bool:
        return (self.ok
                and self.sharpe >= SHARPE_FLOOR
                and self.turnover < TURNOVER_CEILING
                and self.fitness >= FITNESS_FLOOR
                and self.checks_total > 0
                and self.checks_passed == self.checks_total)


def pareto_front(cands: List[Cand]) -> List[Cand]:
    """Pareto on (sharpe↑, fitness↑, -turnover↑, check_ratio↑)."""
    pts = [(c.sharpe, c.fitness, -c.turnover, c.check_ratio) for c in cands]
    keep: List[Cand] = []
    for i, ci in enumerate(cands):
        dominated = False
        for j, cj in enumerate(cands):
            if i == j or not cj.ok:
                continue
            pj = pts[j]; pi = pts[i]
            if all(pj[k] >= pi[k] for k in range(4)) and any(pj[k] > pi[k] for k in range(4)):
                dominated = True; break
        if not dominated and ci.ok:
            keep.append(ci)
    return keep


def select_parents(archive: List[Cand], k: int, rng: random.Random) -> List[Cand]:
    pf = pareto_front(archive)
    pf.sort(key=lambda c: c.score, reverse=True)
    # Top-K from Pareto front; if shorter than k, fill from the rest by score
    if len(pf) >= k:
        return pf[:k]
    rest = sorted([c for c in archive if c.ok and c not in pf],
                  key=lambda c: c.score, reverse=True)
    return pf + rest[:k - len(pf)]


def dedup(exprs: List[str]) -> List[str]:
    seen = set(); out = []
    for e in exprs:
        h = hashlib.md5(e.encode()).hexdigest()
        if h in seen: continue
        seen.add(h); out.append(e)
    return out
