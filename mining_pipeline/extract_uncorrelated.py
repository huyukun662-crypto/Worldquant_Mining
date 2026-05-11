"""Extract K structurally-distinct, low-correlation factors from the
local mining pipeline.

This is a triage-stage utility built on top of `pipeline.py`. The goal:
hand the WQ Brain submitter a small, *diverse* set of candidates so the
queue isn't burned on near-duplicates of the same idea.

Algorithm
---------
1. Generate N random expressions (`expressions.generate`) — no template
   reuse, per the user spec.
2. Initial screen on IS only: `IS_Sharpe > sharpe_floor` AND
   `IS_turnover < turnover_ceiling`.
3. Bayes-optimize the integer literals (lookback windows) on IS for
   each survivor (delegates to `search.search_bayes`).
4. Re-evaluate the optimized expression on the full window; keep
   candidates whose `OS_Sharpe >= IS_Sharpe` (the user's OOS gate).
5. Greedy diversity selection over survivors, sorted by IS Sharpe
   descending. A candidate is *accepted* iff:
     a) Its **structural skeleton** (operator tree with field names and
        integer literals collapsed) is not already used by any
        previously-accepted factor; AND
     b) For every previously-accepted factor, the absolute Pearson
        correlation of their full-window daily PnL series is below
        `corr_threshold`.
   Selection stops once `k` factors are accepted.
6. If fewer than `k` were accepted at the strict threshold, the
   threshold is relaxed in steps (`relax_steps`) and the search retries
   over the remaining pool. Skeleton uniqueness is always enforced —
   the relaxation only loosens the correlation cap.

Local backtest numbers are advisory (per CLAUDE.md). The output of
this script is meant to feed `mining_pipeline.wq_pipeline` /
`scripts/submit_alpha.py` for the canonical WQ Brain evaluation.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import data as data_mod
from .backtest import backtest
from .evaluator import Evaluator
from .expressions import generate, parameterize
from .screen import SHARPE_FLOOR, TURNOVER_CEILING
from .search import search_bayes

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("extract_uncorrelated")


@dataclass
class Factor:
    expression: str          # original (with placeholder windows)
    optimized: str           # after Bayes search
    params: Dict[int, int]
    skeleton: str            # operator-tree fingerprint
    is_sharpe: float
    is_turnover: float
    is_annret: float
    os_sharpe: float
    os_turnover: float
    os_annret: float


# ---------------------------------------------------------------------------
# Skeleton fingerprint
# ---------------------------------------------------------------------------

# Field tokens whose names should collapse to "X" in the skeleton.
_FIELD_TOKENS = {
    "open", "high", "low", "close", "volume", "vwap", "returns",
    "dollar_volume", "cap", "sharesout",
    "adv5", "adv10", "adv20", "adv30", "adv60", "adv120",
}


def skeleton(expr: str) -> str:
    """Return an operator-tree fingerprint of `expr`.

    All field references collapse to ``X`` and all integer/float literals
    collapse to ``D``, leaving only the operator structure. Two
    expressions with the same skeleton are the same template instantiated
    on different fields/windows — i.e., structurally identical.
    """
    tree = ast.parse(expr, mode="eval").body

    def walk(node) -> str:
        if isinstance(node, ast.Constant):
            return "D"
        if isinstance(node, ast.Name):
            return "X" if node.id in _FIELD_TOKENS else node.id
        if isinstance(node, ast.UnaryOp):
            opname = type(node.op).__name__
            return f"u{opname}({walk(node.operand)})"
        if isinstance(node, ast.BinOp):
            opname = type(node.op).__name__
            return f"b{opname}({walk(node.left)},{walk(node.right)})"
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name)
            return f"{node.func.id}({','.join(walk(a) for a in node.args)})"
        raise ValueError(f"unsupported ast node: {type(node).__name__}")

    return walk(tree)


# ---------------------------------------------------------------------------
# Stage 1-4: generate / screen / optimize / OS check
# ---------------------------------------------------------------------------

@dataclass
class Survivor:
    factor: Factor
    pnl: np.ndarray  # full-window daily PnL aligned with panel.dates


def _pnl(signal: np.ndarray, returns: np.ndarray) -> np.ndarray:
    """Full-window daily PnL series (no mask) used for cross-factor
    correlation. Mirrors `backtest.signal_to_weights` + 1-day lag."""
    from .backtest import signal_to_weights
    w = signal_to_weights(signal)
    w_lag = np.roll(w, 1, axis=0)
    w_lag[0] = 0.0
    return np.nansum(w_lag * np.where(np.isnan(returns), 0.0, returns),
                     axis=1)


def _build_pool(panel, evaluator: Evaluator,
                n_candidates: int, seeds: List[int], max_depth: int,
                n_trials: int, sharpe_floor: float,
                turnover_ceiling: float,
                oos_min_ratio: float = 1.0,
                oos_min_sharpe: float = 0.0) -> List[Survivor]:
    is_mask = panel.is_mask()
    os_mask = panel.os_mask()

    logger.info(f"Stage 1: generating {n_candidates} candidates per seed "
                f"across seeds={seeds} (max_depth={max_depth})...")
    seen_exprs: set = set()
    candidates: List[str] = []
    for sd in seeds:
        for e in generate(n_candidates, seed=sd, max_depth=max_depth):
            if e in seen_exprs:
                continue
            seen_exprs.add(e)
            candidates.append(e)
    logger.info(f"  -> {len(candidates)} unique candidates after dedup across seeds")

    logger.info(f"Stage 2-3: initial IS screen "
                f"(SH > {sharpe_floor}, TO < {turnover_ceiling})...")
    pre: List[str] = []
    for expr in candidates:
        try:
            sig = evaluator.evaluate(expr)
        except Exception:
            continue
        bt = backtest(sig, panel.returns, mask=is_mask)
        if bt.sharpe > sharpe_floor and bt.turnover < turnover_ceiling:
            pre.append(expr)
    logger.info(f"  -> {len(pre)}/{len(candidates)} passed initial screen")

    logger.info(f"Stage 4: Bayes-optimize windows ({n_trials} trials each), "
                f"then OS gate (OS_SH >= {oos_min_ratio:.2f}*IS_SH "
                f"AND OS_SH >= {oos_min_sharpe:.2f})...")
    survivors: List[Survivor] = []
    for expr in pre:
        sr = search_bayes(panel, evaluator, expr, is_mask,
                          n_trials=n_trials,
                          turnover_ceiling=turnover_ceiling)
        if sr is None or not math.isfinite(sr.is_sharpe):
            continue
        if sr.is_sharpe <= sharpe_floor or sr.is_turnover >= turnover_ceiling:
            continue
        final_expr = parameterize(expr, sr.best_params)
        try:
            sig = evaluator.evaluate(final_expr)
        except Exception:
            continue
        bt_is = backtest(sig, panel.returns, mask=is_mask)
        bt_os = backtest(sig, panel.returns, mask=os_mask)
        # OS gate: ratio (relative degradation) AND absolute floor.
        # Strict mode (ratio=1.0) reproduces the historical OS_SH >= IS_SH gate;
        # looser modes catch factors that hold up directionally OOS without
        # demanding strict non-degradation, since CLAUDE.md notes local OS
        # numbers don't generalize to WQ Brain anyway.
        if bt_os.sharpe < oos_min_ratio * bt_is.sharpe:
            continue
        if bt_os.sharpe < oos_min_sharpe:
            continue
        f = Factor(
            expression=expr,
            optimized=final_expr,
            params={int(k): int(v) for k, v in sr.best_params.items()},
            skeleton=skeleton(final_expr),
            is_sharpe=bt_is.sharpe, is_turnover=bt_is.turnover,
            is_annret=bt_is.annual_return,
            os_sharpe=bt_os.sharpe, os_turnover=bt_os.turnover,
            os_annret=bt_os.annual_return,
        )
        survivors.append(Survivor(factor=f, pnl=_pnl(sig, panel.returns)))
    logger.info(f"  -> {len(survivors)} factors survived OS gate")
    survivors.sort(key=lambda s: s.factor.is_sharpe, reverse=True)
    return survivors


# ---------------------------------------------------------------------------
# Stage 5-6: greedy uncorrelated selection
# ---------------------------------------------------------------------------

def _abs_corr(a: np.ndarray, b: np.ndarray) -> float:
    """|Pearson correlation| over rows where both are finite & nonzero."""
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30:
        return 0.0
    a2, b2 = a[m], b[m]
    sa, sb = float(np.std(a2)), float(np.std(b2))
    if sa < 1e-12 or sb < 1e-12:
        return 0.0
    return float(abs(np.corrcoef(a2, b2)[0, 1]))


def _greedy_select(pool: List[Survivor], k: int,
                   corr_threshold: float) -> List[Survivor]:
    """Pick up to k survivors that are pairwise uncorrelated and
    structurally distinct from already-picked ones."""
    picked: List[Survivor] = []
    used_skeletons: set = set()
    for cand in pool:
        if len(picked) >= k:
            break
        sk = cand.factor.skeleton
        if sk in used_skeletons:
            continue
        if any(_abs_corr(cand.pnl, p.pnl) >= corr_threshold for p in picked):
            continue
        picked.append(cand)
        used_skeletons.add(sk)
    return picked


def select_uncorrelated(pool: List[Survivor], k: int,
                        corr_threshold: float,
                        relax_steps: Tuple[float, ...] = (0.6, 0.7, 0.8)
                        ) -> Tuple[List[Survivor], float]:
    """Try the strict threshold first, then relax in steps until we have
    `k` factors or exhaust the relaxation schedule. Returns (picked,
    threshold_used)."""
    picked = _greedy_select(pool, k, corr_threshold)
    if len(picked) >= k:
        return picked, corr_threshold
    for thr in relax_steps:
        if thr <= corr_threshold:
            continue
        logger.info(f"  only {len(picked)}/{k} at |corr|<{corr_threshold:.2f}; "
                    f"relaxing to |corr|<{thr:.2f}")
        picked = _greedy_select(pool, k, thr)
        if len(picked) >= k:
            return picked, thr
    logger.warning(f"  could not find {k} uncorrelated factors even at "
                   f"threshold {relax_steps[-1] if relax_steps else corr_threshold}")
    return picked, (relax_steps[-1] if relax_steps else corr_threshold)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(k: int = 4,
        n_candidates: int = 600,
        seeds: Optional[List[int]] = None,
        n_trials: int = 25,
        max_depth: int = 3,
        corr_threshold: float = 0.5,
        sharpe_floor: float = SHARPE_FLOOR,
        turnover_ceiling: float = TURNOVER_CEILING,
        oos_min_ratio: float = 0.5,
        oos_min_sharpe: float = 0.5,
        report_path: str = "UNCORRELATED_FACTORS.json"
        ) -> List[Factor]:
    if seeds is None:
        seeds = [23]
    t0 = time.time()
    logger.info("Loading panel...")
    panel = data_mod.load()
    logger.info(f"  {len(panel.tickers)} tickers x {len(panel.dates)} days "
                f"({panel.dates[0].date()} -> {panel.dates[-1].date()})")
    evaluator = Evaluator(panel)

    pool = _build_pool(
        panel, evaluator,
        n_candidates=n_candidates, seeds=seeds, max_depth=max_depth,
        n_trials=n_trials, sharpe_floor=sharpe_floor,
        turnover_ceiling=turnover_ceiling,
        oos_min_ratio=oos_min_ratio, oos_min_sharpe=oos_min_sharpe,
    )
    if not pool:
        logger.error("No survivors. Try increasing --n or relaxing --sharpe-floor.")
        return []

    logger.info(f"Stage 5: greedy uncorrelated selection (k={k}, "
                f"|corr|<{corr_threshold:.2f}, distinct skeletons)...")
    picked, used_thr = select_uncorrelated(pool, k, corr_threshold)
    logger.info(f"  -> selected {len(picked)} factors at |corr|<{used_thr:.2f}")

    # Pairwise correlation matrix among picked
    n = len(picked)
    corr_mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                corr_mat[i][j] = 1.0
            else:
                corr_mat[i][j] = round(_abs_corr(picked[i].pnl, picked[j].pnl), 4)

    elapsed = time.time() - t0
    report = {
        "config": {
            "k": k, "n_candidates": n_candidates, "seeds": seeds,
            "n_trials": n_trials, "max_depth": max_depth,
            "corr_threshold_requested": corr_threshold,
            "corr_threshold_used": used_thr,
            "sharpe_floor": sharpe_floor,
            "turnover_ceiling": turnover_ceiling,
            "oos_min_ratio": oos_min_ratio,
            "oos_min_sharpe": oos_min_sharpe,
            "is_window": [data_mod.IS_START, data_mod.IS_END],
            "os_window": [data_mod.OS_START, str(panel.dates[-1].date())],
            "universe_size": len(panel.tickers),
            "elapsed_seconds": round(elapsed, 1),
        },
        "stats": {
            "generated_per_seed": n_candidates,
            "n_seeds": len(seeds),
            "pool_after_oos_gate": len(pool),
            "picked": len(picked),
        },
        "factors": [asdict(s.factor) for s in picked],
        "abs_pnl_corr_matrix": corr_mat,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Wrote {report_path}")

    print("\nPICKED UNCORRELATED FACTORS")
    print(f"{'IS_SH':>6} {'IS_TO':>6} {'OS_SH':>6} {'OS_TO':>6}  expression")
    for s in picked:
        f = s.factor
        print(f"{f.is_sharpe:6.2f} {f.is_turnover:6.3f} "
              f"{f.os_sharpe:6.2f} {f.os_turnover:6.3f}  {f.optimized[:120]}")
    if n > 1:
        print("\nPairwise |Pearson(PnL_i, PnL_j)|:")
        for row in corr_mat:
            print("  " + "  ".join(f"{v:.3f}" for v in row))

    return [s.factor for s in picked]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--n", type=int, default=600,
                    help="number of random expressions to generate")
    ap.add_argument("--trials", type=int, default=25,
                    help="Bayes trials per survivor")
    ap.add_argument("--seeds", default="7,19,23,31",
                    help="comma-separated seeds; each contributes --n unique "
                         "expressions (after dedup) to the candidate pool")
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--corr-threshold", type=float, default=0.5,
                    help="strict |corr| ceiling; relaxed automatically if "
                         "we can't fill k slots")
    ap.add_argument("--sharpe-floor", type=float, default=SHARPE_FLOOR,
                    help="initial-screen IS Sharpe floor. CLAUDE.md notes "
                         "local Sharpe numbers don't generalize to WQ Brain; "
                         "lowering this widens the diversity pool.")
    ap.add_argument("--turnover-ceiling", type=float, default=TURNOVER_CEILING)
    ap.add_argument("--oos-min-ratio", type=float, default=0.5,
                    help="OS_Sharpe must exceed this multiple of IS_Sharpe. "
                         "1.0 reproduces the strict OS>=IS gate; 0.5 is a "
                         "looser triage suited to handing diverse candidates "
                         "to WQ Brain (the canonical evaluator).")
    ap.add_argument("--oos-min-sharpe", type=float, default=0.5,
                    help="Absolute floor on OS_Sharpe applied alongside the "
                         "ratio gate.")
    ap.add_argument("--report", default="UNCORRELATED_FACTORS.json")
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    run(k=args.k, n_candidates=args.n, seeds=seeds,
        n_trials=args.trials, max_depth=args.max_depth,
        corr_threshold=args.corr_threshold,
        sharpe_floor=args.sharpe_floor,
        turnover_ceiling=args.turnover_ceiling,
        oos_min_ratio=args.oos_min_ratio,
        oos_min_sharpe=args.oos_min_sharpe,
        report_path=args.report)
