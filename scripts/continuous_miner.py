"""Continuous Factor_Zoo miner — keep mining until N structurally distinct
factors pass the strict gates (IS_SH > 1.25 ∧ IS_TO < 0.25 ∧ OS_SH ≥ IS_SH).

Pulls candidates from:
  (a) curated mechanism-family templates (with placeholder windows that
      Optuna tunes), spanning ~25 structurally distinct skeletons across
      reversal, dispersion, momentum-confirmation, divergence, volatility,
      and microstructure mechanisms;
  (b) random expressions from mining_pipeline.expressions.generate(...).

Per-expression Optuna search budget tuned for throughput.

Persists progress to logs/<session>/continuous_results.json after every
candidate so a crash mid-run preserves work. Stops as soon as N
structurally distinct survivors are accumulated.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import multiprocessing as mp
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
import optuna

from mining_pipeline.backtest import backtest
from mining_pipeline.data import load
from mining_pipeline.evaluator import Evaluator
from mining_pipeline.expressions import (
    generate as random_generate, integer_positions, parameterize,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cmine")

REPO = Path(__file__).resolve().parent.parent
SESSION_DIR = REPO / "logs" / "20260510_continuous_mining"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

IS_SH_FLOOR = 1.25
IS_TO_CEIL = 0.25
WIN_LO, WIN_HI = 3, 60

# 25+ structurally distinct mechanism templates. Each `_` placeholder is a
# tunable integer literal. The miner replaces `_` with default windows
# before parameterization, then Optuna optimizes the integer literals.
TEMPLATES_RAW = [
    # --- Volume-dispersion / abnormal-volume × price-extension ---
    "rank(ts_decay_linear(multiply(divide(ts_std_dev(volume,_),ts_mean(volume,_)),reverse(ts_returns(close,_))),_))",
    "rank(reverse(multiply(ts_zscore(volume,_),ts_zscore(close,_))))",
    "rank(reverse(multiply(divide(ts_std_dev(volume,_),ts_mean(volume,_)),ts_returns(close,_))))",
    "rank(reverse(multiply(divide(volume,ts_mean(volume,_)),ts_zscore(close,_))))",
    "rank(ts_decay_linear(reverse(multiply(ts_zscore(volume,_),ts_returns(vwap,_))),_))",
    "rank(ts_decay_linear(reverse(multiply(divide(ts_std_dev(volume,_),ts_mean(volume,_)),subtract(close,vwap))),_))",
    # --- Price-volume correlation / divergence ---
    "rank(ts_decay_linear(reverse(ts_corr(close,volume,_)),_))",
    "rank(reverse(ts_corr(close,volume,_)))",
    "rank(ts_decay_linear(ts_corr(volume,returns,_),_))",
    "rank(reverse(ts_corr(returns,volume,_)))",
    # --- Idiosyncratic vol / mean-reversion ---
    "rank(reverse(multiply(ts_std_dev(returns,_),ts_returns(close,_))))",
    "rank(ts_decay_linear(reverse(multiply(ts_std_dev(returns,_),ts_returns(close,_))),_))",
    "rank(divide(subtract(close,ts_mean(close,_)),ts_std_dev(close,_)))",
    "rank(reverse(divide(subtract(close,ts_mean(close,_)),ts_std_dev(close,_))))",
    "rank(reverse(ts_zscore(returns,_)))",
    "rank(ts_decay_linear(reverse(ts_zscore(close,_)),_))",
    # --- Microstructure: VWAP / close deviation ---
    "rank(ts_decay_linear(divide(subtract(close,vwap),vwap),_))",
    "rank(ts_decay_linear(reverse(divide(subtract(close,vwap),vwap)),_))",
    "rank(reverse(divide(subtract(close,ts_mean(vwap,_)),ts_std_dev(vwap,_))))",
    # --- Range / extremes ---
    "rank(reverse(divide(close,ts_max(close,_))))",
    "rank(reverse(divide(ts_min(close,_),close)))",
    "rank(divide(subtract(high,low),close))",
    "rank(ts_decay_linear(divide(subtract(high,low),close),_))",
    # --- Volume-rank × price-rank combinations ---
    "rank(reverse(multiply(ts_rank(volume,_),ts_rank(close,_))))",
    "rank(multiply(ts_rank(volume,_),reverse(ts_rank(returns,_))))",
    "rank(reverse(multiply(ts_rank(volume,_),ts_returns(close,_))))",
    # --- Smoothed momentum / signal-decomposition ---
    "rank(ts_decay_linear(ts_returns(close,_),_))",
    "rank(reverse(ts_delta(close,_)))",
    "rank(ts_decay_linear(reverse(ts_delta(close,_)),_))",
    # --- Volume-direction interactions ---
    "rank(ts_decay_linear(multiply(ts_returns(close,_),sign(ts_returns(volume,_))),_))",
    "rank(reverse(multiply(ts_returns(close,_),sign(ts_returns(volume,_)))))",
    "rank(ts_decay_linear(ts_delta(divide(volume,ts_mean(volume,_)),_),_))",
    # --- Long/short vol-of-vol ---
    "rank(reverse(divide(ts_std_dev(returns,_),ts_std_dev(returns,_))))",
    "rank(divide(ts_std_dev(returns,_),ts_mean(abs(returns),_)))",
    # --- Adv20-relative (using volume only, no adv field) ---
    "rank(ts_decay_linear(reverse(multiply(divide(volume,ts_mean(volume,_)),ts_returns(close,_))),_))",
    # --- Composite scaled signals ---
    "rank(scale(reverse(subtract(close,ts_mean(close,_)))))",
    "rank(scale(reverse(ts_zscore(close,_))))",
]


def expand_template(t: str) -> str:
    """Convert standalone `_` placeholders to default windows that downstream
    code can parameterize. Only `_` not adjacent to alnum chars (i.e. not
    part of an identifier like `ts_mean`) is replaced.
    """
    return re.sub(r"(?<![A-Za-z0-9_])_(?![A-Za-z0-9_])", "20", t)


def structural_signature(expr: str) -> str:
    """Canonicalize: replace every standalone integer literal with `_`,
    then collapse whitespace. Two expressions with the same signature
    differ only in window values."""
    out = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isdigit() and (i == 0 or not (expr[i - 1].isalnum() or expr[i - 1] == "_")):
            k = i
            while k < n and (expr[k].isdigit() or expr[k] == "."):
                k += 1
            tok = expr[i:k]
            if "." not in tok:
                out.append("_")
            else:
                out.append(tok)
            i = k
        else:
            out.append(ch)
            i += 1
    return re.sub(r"\s+", "", "".join(out))


@dataclass
class CandidateResult:
    base_expr: str
    optimized_expr: str
    structural_sig: str
    best_windows: dict
    is_sharpe: float
    is_turnover: float
    is_ann_return: float
    os_sharpe: float
    os_turnover: float
    os_ann_return: float
    n_trials: int
    survivor: bool
    error: str = ""


def _evaluate(panel, evaluator, expr, params, mask):
    final = parameterize(expr, params) if params else expr
    try:
        signal = evaluator.evaluate(final)
    except Exception as exc:
        return None, None, None, str(exc)
    if not isinstance(signal, np.ndarray) or signal.shape != panel.close.shape:
        return None, None, None, "bad_shape"
    bt = backtest(signal, panel.returns, mask=mask)
    return bt.sharpe, bt.turnover, bt.annual_return, ""


def search_candidate(panel, evaluator, expr, n_trials, seed) -> CandidateResult:
    is_mask = panel.is_mask()
    os_mask = panel.os_mask()
    positions = integer_positions(expr)

    # Ensure parsable
    try:
        evaluator.evaluate(expr)
    except Exception as exc:
        return CandidateResult(expr, expr, structural_signature(expr), {},
                               0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0,
                               survivor=False, error=f"parse:{exc}"[:200])

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    def objective(trial):
        params = {p: trial.suggest_int(f"w{p}", WIN_LO, WIN_HI) for p in positions}
        sh, tv, _, err = _evaluate(panel, evaluator, expr, params, is_mask)
        if sh is None or not math.isfinite(sh):
            return -10.0
        return sh - (5.0 if tv >= IS_TO_CEIL else 0.0)

    if positions:
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        best = {int(k[1:]): v for k, v in study.best_params.items()}
    else:
        best = {}
    final = parameterize(expr, best) if best else expr

    is_sh, is_to, is_ar, err_is = _evaluate(panel, evaluator, expr, best, is_mask)
    os_sh, os_to, os_ar, err_os = _evaluate(panel, evaluator, expr, best, os_mask)

    if err_is or err_os or is_sh is None or os_sh is None:
        return CandidateResult(expr, final, structural_signature(final), best,
                               0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                               len(study.trials) if positions else 0,
                               survivor=False,
                               error=(err_is or err_os)[:200])

    survivor = (is_sh > IS_SH_FLOOR and is_to < IS_TO_CEIL and os_sh >= is_sh)
    return CandidateResult(
        base_expr=expr, optimized_expr=final,
        structural_sig=structural_signature(final),
        best_windows=best,
        is_sharpe=float(is_sh), is_turnover=float(is_to),
        is_ann_return=float(is_ar) if is_ar is not None else 0.0,
        os_sharpe=float(os_sh), os_turnover=float(os_to),
        os_ann_return=float(os_ar) if os_ar is not None else 0.0,
        n_trials=len(study.trials) if positions else 0,
        survivor=survivor,
    )


# --- Worker for multiprocessing ---
_WORKER_PANEL = None
_WORKER_EVAL = None


def _worker_init():
    global _WORKER_PANEL, _WORKER_EVAL
    _WORKER_PANEL = load(use_cache=True)
    _WORKER_EVAL = Evaluator(_WORKER_PANEL)
    optuna.logging.set_verbosity(optuna.logging.WARNING)


def _worker_run(args):
    expr, n_trials, seed = args
    try:
        return search_candidate(_WORKER_PANEL, _WORKER_EVAL, expr, n_trials, seed)
    except Exception as exc:
        return CandidateResult(expr, expr, structural_signature(expr), {},
                               0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0,
                               survivor=False, error=f"worker:{exc}"[:200])


def candidate_stream(seed: int):
    """Yield candidate base-expressions: templates first, then unbounded random."""
    # Pass 1: curated mechanism templates (each with default windows)
    for t in TEMPLATES_RAW:
        yield ("template", expand_template(t))
    # Pass 2: random generator, unbounded
    rng_seed = seed
    while True:
        batch = random_generate(50, seed=rng_seed, max_depth=3)
        for e in batch:
            yield ("random", e)
        rng_seed += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=4)
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--max-candidates", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260510)
    ap.add_argument("--workers", type=int, default=4,
                     help="Parallel workers (1 disables multiprocessing)")
    args = ap.parse_args()

    log.info("Loading panel")
    panel = load(use_cache=True)
    log.info(f"   {len(panel.tickers)} tickers x {len(panel.dates)} days "
             f"({panel.dates[0].date()} -> {panel.dates[-1].date()})")
    evaluator = Evaluator(panel)

    out_path = SESSION_DIR / "continuous_results.json"
    state_path = SESSION_DIR / "miner_state.json"

    all_results: list[CandidateResult] = []
    distinct_survivors: dict[str, CandidateResult] = {}  # sig -> best result
    seen_sigs: set[str] = set()
    n_processed = 0

    # Resume support
    if out_path.exists():
        try:
            with open(out_path) as f:
                prior = json.load(f)
            for r in prior.get("all_results", []):
                all_results.append(CandidateResult(**r))
                seen_sigs.add(r["structural_sig"])
            for r in prior.get("survivors", []):
                if r["structural_sig"] not in distinct_survivors:
                    distinct_survivors[r["structural_sig"]] = CandidateResult(**r)
            n_processed = prior.get("n_processed", len(all_results))
            log.info(f"resumed: prior={n_processed} candidates, "
                     f"{len(distinct_survivors)} survivors, {len(seen_sigs)} sigs")
        except Exception as exc:
            log.warning(f"resume failed: {exc}; starting fresh")
            all_results = []
            distinct_survivors = {}
            seen_sigs = set()
            n_processed = 0
    t0 = time.time()

    def persist():
        with open(out_path, "w") as f:
            json.dump({
                "n_processed": n_processed,
                "elapsed_s": time.time() - t0,
                "n_distinct_survivors": len(distinct_survivors),
                "target": args.target,
                "survivors": [asdict(v) for v in distinct_survivors.values()],
                "all_results": [asdict(rr) for rr in all_results],
            }, f, indent=2)
        with open(state_path, "w") as f:
            json.dump({"n_processed": n_processed,
                        "n_distinct_survivors": len(distinct_survivors)}, f)

    def handle_result(r: CandidateResult):
        nonlocal n_processed
        n_processed += 1
        elapsed = time.time() - t0
        rate = n_processed / max(elapsed, 1)
        all_results.append(r)
        if r.survivor:
            sig = r.structural_sig
            if sig not in distinct_survivors or r.is_sharpe > distinct_survivors[sig].is_sharpe:
                is_new = sig not in distinct_survivors
                distinct_survivors[sig] = r
                marker = "NEW" if is_new else "BETTER"
                log.info(f"*** SURVIVOR {marker} #{len(distinct_survivors)} "
                         f"IS_SH={r.is_sharpe:+.3f} IS_TO={r.is_turnover:.3f} "
                         f"OS_SH={r.os_sharpe:+.3f} | {r.optimized_expr[:90]}")
                persist()
        if n_processed % 10 == 0:
            log.info(f"[{n_processed}] elapsed={elapsed:.0f}s rate={rate:.2f}/s "
                     f"survivors={len(distinct_survivors)}/{args.target}")
            persist()

    # Build candidate batch in advance, deduplicated
    def fresh_candidates(n: int):
        out = []
        for source, expr in candidate_stream(args.seed):
            sig = structural_signature(expr)
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            out.append((expr, args.trials, args.seed + n_processed + len(out) + 1))
            if len(out) >= n:
                break
        return out

    if args.workers <= 1:
        for source, expr in candidate_stream(args.seed):
            if n_processed >= args.max_candidates:
                log.info(f"Reached max-candidates {args.max_candidates}")
                break
            if len(distinct_survivors) >= args.target:
                log.info(f"Reached target of {args.target} structurally distinct survivors")
                break
            sig = structural_signature(expr)
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            r = search_candidate(panel, evaluator, expr, args.trials,
                                  args.seed + n_processed + 1)
            handle_result(r)
    else:
        log.info(f"Parallel mining with {args.workers} workers")
        ctx = mp.get_context("spawn")
        with ctx.Pool(args.workers, initializer=_worker_init) as pool:
            while (n_processed < args.max_candidates
                    and len(distinct_survivors) < args.target):
                batch_size = min(args.workers * 4,
                                  args.max_candidates - n_processed)
                batch = fresh_candidates(batch_size)
                if not batch:
                    log.info("Candidate stream exhausted")
                    break
                for r in pool.imap_unordered(_worker_run, batch):
                    handle_result(r)
                    if len(distinct_survivors) >= args.target:
                        break
                if len(distinct_survivors) >= args.target:
                    log.info(f"Reached target of {args.target} structurally distinct survivors")
                    break

    # Final write
    survivors_list = list(distinct_survivors.values())
    survivors_list.sort(key=lambda r: r.is_sharpe, reverse=True)

    with open(out_path, "w") as f:
        json.dump({
            "n_processed": n_processed,
            "elapsed_s": time.time() - t0,
            "n_distinct_survivors": len(distinct_survivors),
            "target": args.target,
            "survivors": [asdict(v) for v in survivors_list],
            "all_results": [asdict(r) for r in all_results],
        }, f, indent=2)

    print()
    print("=" * 100)
    print(f"Processed: {n_processed}")
    print(f"Distinct survivors: {len(distinct_survivors)}/{args.target}")
    if distinct_survivors:
        print()
        print(f"{'IS_SH':>7}{'IS_TO':>7}{'OS_SH':>7}{'OS_TO':>7}  expression")
        for r in survivors_list:
            print(f"{r.is_sharpe:7.3f}{r.is_turnover:7.3f}"
                  f"{r.os_sharpe:7.3f}{r.os_turnover:7.3f}  {r.optimized_expr}")
    print("=" * 100)


if __name__ == "__main__":
    main()
