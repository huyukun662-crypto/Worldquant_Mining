"""Hyperparameter search over expression lookback windows.

For a given expression with K integer literals, search.py optimizes the
windows on **IS only**. Two backends are supported:

* `bayes`: Bayesian optimization via Optuna's TPE sampler.
* `grid`:  Cartesian grid over `WINDOWS_GRID`.

Objective:  IS Sharpe, with hard constraint that turnover < CEILING.
            (Constraint is enforced by returning a large negative score
            whenever turnover violates the cap.)
"""

from __future__ import annotations

import itertools
import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from .backtest import backtest
from .data import Panel
from .evaluator import Evaluator
from .expressions import integer_positions, parameterize
from .screen import SHARPE_FLOOR, TURNOVER_CEILING

logger = logging.getLogger(__name__)

WINDOWS_GRID = (3, 5, 10, 20, 40, 60)
WINDOWS_RANGE = (3, 60)


@dataclass
class SearchResult:
    expression: str
    best_params: dict
    is_sharpe: float
    is_turnover: float
    is_annret: float
    n_evals: int


def _evaluate(panel: Panel, evaluator: Evaluator, expr: str,
              params: dict, mask: np.ndarray) -> Tuple[float, float]:
    final = parameterize(expr, params)
    try:
        signal = evaluator.evaluate(final)
    except Exception:
        return -math.inf, math.inf
    if not isinstance(signal, np.ndarray) or signal.shape != panel.close.shape:
        return -math.inf, math.inf
    bt = backtest(signal, panel.returns, mask=mask)
    return bt.sharpe, bt.turnover


def search_grid(panel: Panel, evaluator: Evaluator, expr: str,
                is_mask: np.ndarray,
                turnover_ceiling: float = TURNOVER_CEILING
                ) -> Optional[SearchResult]:
    positions = integer_positions(expr)
    if not positions:
        sh, tv = _evaluate(panel, evaluator, expr, {}, is_mask)
        if not math.isfinite(sh):
            return None
        return SearchResult(expr, {}, sh, tv, 0.0, 1)
    grids = [WINDOWS_GRID for _ in positions]
    best: Optional[Tuple[float, dict, float]] = None
    n = 0
    for combo in itertools.product(*grids):
        params = {p: v for p, v in zip(positions, combo)}
        sh, tv = _evaluate(panel, evaluator, expr, params, is_mask)
        n += 1
        if not math.isfinite(sh):
            continue
        score = sh if tv < turnover_ceiling else sh - 5.0
        if best is None or score > best[0]:
            best = (score, dict(params), tv)
    if best is None:
        return None
    final = parameterize(expr, best[1])
    sh, tv = _evaluate(panel, evaluator, expr, best[1], is_mask)
    return SearchResult(expr, best[1], sh, tv, 0.0, n)


def search_bayes(panel: Panel, evaluator: Evaluator, expr: str,
                 is_mask: np.ndarray,
                 n_trials: int = 30,
                 turnover_ceiling: float = TURNOVER_CEILING,
                 seed: int = 0) -> Optional[SearchResult]:
    import optuna
    positions = integer_positions(expr)
    if not positions:
        sh, tv = _evaluate(panel, evaluator, expr, {}, is_mask)
        if not math.isfinite(sh):
            return None
        return SearchResult(expr, {}, sh, tv, 0.0, 1)

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: "optuna.trial.Trial") -> float:
        params = {p: trial.suggest_int(f"w{p}", *WINDOWS_RANGE)
                  for p in positions}
        sh, tv = _evaluate(panel, evaluator, expr, params, is_mask)
        if not math.isfinite(sh):
            return -10.0
        return sh - (5.0 if tv >= turnover_ceiling else 0.0)

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    best = {int(k[1:]): v for k, v in study.best_params.items()}
    sh, tv = _evaluate(panel, evaluator, expr, best, is_mask)
    return SearchResult(expr, best, sh, tv, 0.0, n_trials)
