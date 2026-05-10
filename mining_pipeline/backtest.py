"""Vectorized long-short backtest.

Given a (T, N) factor signal, compute:
    - daily portfolio returns from rank-weighted long-short positions
    - annualized Sharpe ratio
    - average daily turnover

Conventions
-----------
* Signal is converted to portfolio weights cross-sectionally per row by
  demeaning + L1-normalizing so sum(|w|) == 1 (i.e. always 100% gross).
* Position is held from t -> t+1; PnL on day t+1 is `w_t * ret_{t+1}`.
* Turnover_t = 0.5 * sum_i |w_t - w_{t-1}|.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


TRADING_DAYS = 252


@dataclass
class BTResult:
    sharpe: float
    annual_return: float
    annual_vol: float
    turnover: float
    n_days: int
    pnl: np.ndarray  # daily portfolio returns aligned with `dates_mask`


def signal_to_weights(signal: np.ndarray) -> np.ndarray:
    """Cross-sectional demean + L1-normalize per row -> (T, N) weights."""
    T, N = signal.shape
    w = np.where(np.isnan(signal), 0.0, signal)
    # demean per row over non-NaN values
    valid = ~np.isnan(signal)
    counts = valid.sum(axis=1, keepdims=True)
    means = (w * valid).sum(axis=1, keepdims=True) / np.maximum(counts, 1)
    w = (w - means) * valid
    # L1 normalize
    s = np.abs(w).sum(axis=1, keepdims=True)
    s[s < 1e-12] = 1.0
    w = w / s
    return w


def backtest(signal: np.ndarray, returns: np.ndarray,
             mask: Optional[np.ndarray] = None) -> BTResult:
    """Run backtest on the rows where `mask` is True (or all rows if None)."""
    if mask is None:
        mask = np.ones(signal.shape[0], dtype=bool)
    w_full = signal_to_weights(signal)
    # Align: position at end of t -> realized at t+1 with returns[t+1]
    w_lag = np.roll(w_full, 1, axis=0)
    w_lag[0] = 0.0
    pnl_full = np.nansum(w_lag * np.where(np.isnan(returns), 0.0, returns), axis=1)
    # restrict to mask
    pnl = pnl_full[mask]
    if pnl.size < 2 or np.nanstd(pnl) < 1e-12:
        return BTResult(sharpe=0.0, annual_return=0.0, annual_vol=0.0,
                        turnover=0.0, n_days=int(pnl.size), pnl=pnl)
    mu = float(np.nanmean(pnl))
    sd = float(np.nanstd(pnl, ddof=0))
    sharpe = (mu / sd) * np.sqrt(TRADING_DAYS)
    # turnover: |w_t - w_{t-1}| / 2  (one-sided), averaged
    dw = np.abs(w_full[1:] - w_full[:-1]).sum(axis=1) * 0.5
    # restrict turnover to mask rows that are valid t>=1
    if mask[1:].sum() > 0:
        turnover = float(np.nanmean(dw[mask[1:]]))
    else:
        turnover = 0.0
    return BTResult(
        sharpe=float(sharpe),
        annual_return=float(mu * TRADING_DAYS),
        annual_vol=float(sd * np.sqrt(TRADING_DAYS)),
        turnover=turnover,
        n_days=int(pnl.size),
        pnl=pnl,
    )
