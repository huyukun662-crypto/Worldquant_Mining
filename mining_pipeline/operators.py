"""Numpy implementations of canonical WorldQuant operators.

Only the subset needed by `expressions.py` is implemented here. Each
operator takes (T, N) numpy arrays and returns a (T, N) numpy array,
with NaN-aware semantics.

Names match `worldquant_mining.operators` exactly.
"""

from __future__ import annotations

import numpy as np

EPS = 1e-12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rolling_apply(x: np.ndarray, d: int, func) -> np.ndarray:
    """Apply `func(window)` over the last d rows for every (t, j); pure numpy."""
    T, N = x.shape
    out = np.full_like(x, np.nan, dtype=np.float64)
    for t in range(d - 1, T):
        window = x[t - d + 1: t + 1]
        out[t] = func(window)
    return out


# ---------------------------------------------------------------------------
# Arithmetic / element-wise
# ---------------------------------------------------------------------------

def add(x, y): return x + y
def subtract(x, y): return x - y
def multiply(x, y): return x * y
def divide(x, y):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.abs(y) < EPS, np.nan, x / y)
def reverse(x): return -x
def sign(x): return np.sign(x)
def abs_(x): return np.abs(x)
def log(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(x > 0, np.log(x), np.nan)
def signed_power(x, p):
    return np.sign(x) * np.power(np.abs(x), p)
def power(x, p): return np.power(x, p)
def s_log_1p(x):
    return np.sign(x) * np.log1p(np.abs(x))


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------

def ts_delay(x, d):
    out = np.full_like(x, np.nan, dtype=np.float64)
    if d <= 0:
        return x.astype(np.float64).copy()
    out[d:] = x[:-d]
    return out


def ts_delta(x, d):
    return x - ts_delay(x, d)


def ts_sum(x, d):
    T, N = x.shape
    out = np.full_like(x, np.nan, dtype=np.float64)
    if d <= 0 or d > T:
        return out
    cs = np.nancumsum(x, axis=0)
    out[d - 1:] = cs[d - 1:]
    out[d:] = cs[d:] - cs[:-d]
    return out


def ts_mean(x, d):
    return ts_sum(x, d) / d


def ts_std_dev(x, d):
    return _rolling_apply(x, d, lambda w: np.nanstd(w, axis=0, ddof=0))


def ts_zscore(x, d):
    m = ts_mean(x, d)
    s = ts_std_dev(x, d)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s < EPS, np.nan, (x - m) / s)


def ts_rank(x, d):
    """Time-series rank of last value within last d obs, scaled to [0, 1]."""
    def _rank_last(w):
        last = w[-1]
        # rank of `last` within window for each column
        order = np.argsort(np.argsort(w, axis=0), axis=0)  # 0..d-1
        rank = order[-1].astype(np.float64) / max(w.shape[0] - 1, 1)
        # NaN if last is NaN
        return np.where(np.isnan(last), np.nan, rank)
    return _rolling_apply(x, d, _rank_last)


def ts_min(x, d):
    return _rolling_apply(x, d, lambda w: np.nanmin(w, axis=0))


def ts_max(x, d):
    return _rolling_apply(x, d, lambda w: np.nanmax(w, axis=0))


def ts_arg_max(x, d):
    return _rolling_apply(x, d, lambda w: np.argmax(np.where(np.isnan(w), -np.inf, w), axis=0).astype(np.float64))


def ts_arg_min(x, d):
    return _rolling_apply(x, d, lambda w: np.argmin(np.where(np.isnan(w), np.inf, w), axis=0).astype(np.float64))


def ts_corr(x, y, d):
    def _corr(wx, wy):
        mx = np.nanmean(wx, axis=0)
        my = np.nanmean(wy, axis=0)
        ax, ay = wx - mx, wy - my
        num = np.nansum(ax * ay, axis=0)
        denom = np.sqrt(np.nansum(ax * ax, axis=0) * np.nansum(ay * ay, axis=0))
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(denom < EPS, np.nan, num / denom)
    T, N = x.shape
    out = np.full_like(x, np.nan, dtype=np.float64)
    for t in range(d - 1, T):
        out[t] = _corr(x[t - d + 1:t + 1], y[t - d + 1:t + 1])
    return out


def ts_decay_linear(x, d):
    weights = np.arange(1, d + 1, dtype=np.float64)
    weights /= weights.sum()
    T, N = x.shape
    out = np.full_like(x, np.nan, dtype=np.float64)
    for t in range(d - 1, T):
        w = x[t - d + 1:t + 1]
        # Mask NaNs: use renormalized weights per column
        mask = ~np.isnan(w)
        wmat = np.broadcast_to(weights[:, None], w.shape).copy()
        wmat[~mask] = 0.0
        wsum = wmat.sum(axis=0)
        # avoid 0-division
        with np.errstate(divide="ignore", invalid="ignore"):
            out[t] = np.where(wsum < EPS, np.nan,
                              np.nansum(np.where(mask, w * wmat, 0.0), axis=0) / wsum)
    return out


def ts_returns(x, d):
    prev = ts_delay(x, d)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.abs(prev) < EPS, np.nan, x / prev - 1.0)


# ---------------------------------------------------------------------------
# Cross sectional
# ---------------------------------------------------------------------------

def rank(x):
    """Cross-sectional rank in [0, 1] computed per row, NaN-aware."""
    T, N = x.shape
    out = np.full_like(x, np.nan, dtype=np.float64)
    for t in range(T):
        row = x[t]
        mask = ~np.isnan(row)
        if mask.sum() < 2:
            continue
        order = np.argsort(np.argsort(row[mask]))
        ranks = order.astype(np.float64) / (mask.sum() - 1)
        out[t, mask] = ranks
    return out


def zscore(x):
    m = np.nanmean(x, axis=1, keepdims=True)
    s = np.nanstd(x, axis=1, keepdims=True, ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s < EPS, np.nan, (x - m) / s)


def scale(x, target=1.0):
    """Cross-sectionally scale so that sum(|x_t|) == target on each row."""
    s = np.nansum(np.abs(x), axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s < EPS, np.nan, target * x / s)


def winsorize(x, std=4.0):
    m = np.nanmean(x, axis=1, keepdims=True)
    s = np.nanstd(x, axis=1, keepdims=True, ddof=0)
    lo = m - std * s
    hi = m + std * s
    return np.clip(x, lo, hi)


def normalize(x):
    """Demean per row."""
    return x - np.nanmean(x, axis=1, keepdims=True)


# Map for the evaluator
NUMPY_OPS = {
    # arithmetic
    "add": add, "subtract": subtract, "multiply": multiply, "divide": divide,
    "reverse": reverse, "sign": sign, "abs": abs_, "log": log,
    "power": power, "signed_power": signed_power, "s_log_1p": s_log_1p,
    # time series
    "ts_delay": ts_delay, "ts_delta": ts_delta, "ts_sum": ts_sum,
    "ts_mean": ts_mean, "ts_std_dev": ts_std_dev, "ts_zscore": ts_zscore,
    "ts_rank": ts_rank, "ts_min": ts_min, "ts_max": ts_max,
    "ts_arg_max": ts_arg_max, "ts_arg_min": ts_arg_min,
    "ts_corr": ts_corr, "ts_decay_linear": ts_decay_linear,
    "ts_returns": ts_returns,
    # cross sectional
    "rank": rank, "zscore": zscore, "scale": scale,
    "winsorize": winsorize, "normalize": normalize,
}
