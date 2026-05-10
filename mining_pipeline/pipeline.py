"""End-to-end mining pipeline.

Stages:
    1. Generate N random expressions (no Alpha101/classical reuse).
    2. Evaluate IS Sharpe + turnover with the *initial* lookbacks
       (default windows from the generator).
    3. Initial screen: keep expressions with IS_Sharpe > 1.25
       AND turnover < 0.25.
    4. Hyperparameter search (Bayes or grid) on each survivor's
       integer-literal lookbacks, IS only.
    5. Re-evaluate optimized expressions on OS (2024-now).
    6. Final filter: OOS_Sharpe >= IS_Sharpe (per user spec).
    7. Sort survivors by IS Sharpe and write report.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass
from typing import List

import numpy as np

from . import data as data_mod
from .backtest import backtest
from .evaluator import Evaluator
from .expressions import generate, parameterize
from .screen import SHARPE_FLOOR, TURNOVER_CEILING, screen
from .search import search_bayes, search_grid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("pipeline")


@dataclass
class CandidateResult:
    expression: str
    optimized: str
    params: dict
    is_sharpe: float
    is_turnover: float
    is_annret: float
    os_sharpe: float
    os_turnover: float
    os_annret: float


def run(n_candidates: int = 300,
        seed: int = 7,
        backend: str = "bayes",
        n_trials: int = 25,
        sharpe_floor: float = SHARPE_FLOOR,
        turnover_ceiling: float = TURNOVER_CEILING,
        report_path: str = "MINING_REPORT.json",
        max_depth: int = 3) -> List[CandidateResult]:

    t0 = time.time()
    logger.info("Loading panel...")
    panel = data_mod.load()
    logger.info(f"  {len(panel.tickers)} tickers x {len(panel.dates)} days "
                f"({panel.dates[0].date()} -> {panel.dates[-1].date()})")
    is_mask = panel.is_mask()
    os_mask = panel.os_mask()
    logger.info(f"  IS days: {is_mask.sum()}   OS days: {os_mask.sum()}")

    evaluator = Evaluator(panel)

    logger.info(f"Stage 1: generating {n_candidates} candidate expressions (no template reuse)...")
    candidates = generate(n_candidates, seed=seed, max_depth=max_depth)

    logger.info("Stage 2-3: initial IS screen (Sharpe > %.2f AND turnover < %.2f)..."
                % (sharpe_floor, turnover_ceiling))
    survivors: List[str] = []
    for i, expr in enumerate(candidates):
        try:
            sig = evaluator.evaluate(expr)
        except Exception as e:
            continue
        bt = backtest(sig, panel.returns, mask=is_mask)
        if bt.sharpe > sharpe_floor and bt.turnover < turnover_ceiling:
            survivors.append(expr)
    logger.info(f"  -> {len(survivors)}/{len(candidates)} candidates passed initial screen")

    logger.info(f"Stage 4: hyperparameter search ({backend}) on survivors...")
    optimized: list[CandidateResult] = []
    search_fn = (lambda e: search_bayes(panel, evaluator, e, is_mask,
                                        n_trials=n_trials,
                                        turnover_ceiling=turnover_ceiling)) \
                if backend == "bayes" else \
                (lambda e: search_grid(panel, evaluator, e, is_mask,
                                       turnover_ceiling=turnover_ceiling))
    for i, expr in enumerate(survivors):
        sr = search_fn(expr)
        if sr is None or not math.isfinite(sr.is_sharpe):
            continue
        if sr.is_sharpe <= sharpe_floor or sr.is_turnover >= turnover_ceiling:
            continue
        # Stage 5: OS evaluation
        final = parameterize(expr, sr.best_params)
        try:
            sig = evaluator.evaluate(final)
        except Exception:
            continue
        bt_is = backtest(sig, panel.returns, mask=is_mask)
        bt_os = backtest(sig, panel.returns, mask=os_mask)
        # Stage 6: OOS >= IS check
        if bt_os.sharpe < bt_is.sharpe:
            continue
        optimized.append(CandidateResult(
            expression=expr,
            optimized=final,
            params=sr.best_params,
            is_sharpe=bt_is.sharpe, is_turnover=bt_is.turnover, is_annret=bt_is.annual_return,
            os_sharpe=bt_os.sharpe, os_turnover=bt_os.turnover, os_annret=bt_os.annual_return,
        ))

    optimized.sort(key=lambda r: r.is_sharpe, reverse=True)
    elapsed = time.time() - t0
    logger.info(f"Stage 7: {len(optimized)} factors survived OOS>=IS (took {elapsed:.1f}s)")

    if optimized:
        report = {
            "config": {
                "n_candidates": n_candidates, "seed": seed, "backend": backend,
                "n_trials": n_trials, "sharpe_floor": sharpe_floor,
                "turnover_ceiling": turnover_ceiling, "max_depth": max_depth,
                "is_window": [data_mod.IS_START, data_mod.IS_END],
                "os_window": [data_mod.OS_START, str(panel.dates[-1].date())],
                "universe_size": len(panel.tickers),
                "elapsed_seconds": round(elapsed, 1),
            },
            "stats": {
                "generated": n_candidates,
                "passed_screen": len(survivors),
                "survived_oos_check": len(optimized),
            },
            "factors": [asdict(r) for r in optimized],
        }
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Wrote {report_path}")
        # Print top 20 to stdout
        print("\nTOP FACTORS (sorted by IS Sharpe):")
        print(f"{'IS_SH':>6} {'IS_TO':>6} {'OS_SH':>6} {'OS_TO':>6}  expression")
        for r in optimized[:20]:
            print(f"{r.is_sharpe:6.2f} {r.is_turnover:6.3f} {r.os_sharpe:6.2f} "
                  f"{r.os_turnover:6.3f}  {r.optimized[:120]}")
    else:
        logger.warning("No factors survived all stages.")

    return optimized


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--backend", choices=("bayes", "grid"), default="bayes")
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    run(n_candidates=args.n, backend=args.backend, n_trials=args.trials, seed=args.seed)
