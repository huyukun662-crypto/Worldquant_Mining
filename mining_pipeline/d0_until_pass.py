"""D0 mining loop: keep submitting expressions until one passes all IS
checks on WQ Brain.

A "winner" is a simulation whose `is.checks` are ALL `PASS` (i.e. the
alpha is submit-eligible). The loop:
  1. Generates a batch of D0-shaped expressions (`expressions.generate`).
  2. For each expression, runs a small Optuna study over the joint
     (expression-windows, simulation-settings) space via
     `wq_pipeline.search_one`.
  3. Appends every trial result to `D0_MINING_REPORT.json` (idempotent).
  4. If any trial returns `checks_passed == checks_total`, writes
     `D0_WINNER.json` and exits 0.
  5. Otherwise repeats until `--max-sims` or `--max-hours` runs out.

Container reclaim resilience: `D0_PROGRESS.json` records the cumulative
sim counter and iteration so a fresh invocation can resume.

Run:
    python -m mining_pipeline.d0_until_pass --max-sims 200 --max-hours 6
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .expressions import generate
from .wq_pipeline import search_one, SHARPE_FLOOR, TURNOVER_CEILING

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("d0-loop")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

REPORT = REPO / "D0_MINING_REPORT.json"
WINNER = REPO / "D0_WINNER.json"
PROGRESS = REPO / "D0_PROGRESS.json"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_report() -> list[dict]:
    if REPORT.exists():
        try:
            return json.loads(REPORT.read_text())
        except json.JSONDecodeError:
            return []
    return []


def _save_report(rows: list[dict]) -> None:
    REPORT.write_text(json.dumps(rows, indent=2))


def _load_progress() -> dict:
    if PROGRESS.exists():
        try:
            return json.loads(PROGRESS.read_text())
        except json.JSONDecodeError:
            pass
    return {"iteration": 0, "sims_used": 0, "start_time": time.time()}


def _save_progress(p: dict) -> None:
    PROGRESS.write_text(json.dumps(p, indent=2))


def _is_winner(r) -> bool:
    return bool(r.ok and r.checks_total > 0
                and r.checks_passed == r.checks_total)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-sims",  type=int,   default=200,
                    help="hard cap on cumulative WQ simulations submitted")
    ap.add_argument("--max-hours", type=float, default=6.0,
                    help="hard wall-clock cap in hours")
    ap.add_argument("--batch",     type=int,   default=8,
                    help="expressions generated per iteration")
    ap.add_argument("--trials",    type=int,   default=4,
                    help="Optuna trials (== simulations) per expression")
    ap.add_argument("--max-depth", type=int,   default=3)
    ap.add_argument("--seed",      type=int,   default=41)
    args = ap.parse_args()

    if WINNER.exists():
        log.info(f"{WINNER} already exists; nothing to do. Delete it to retry.")
        return 0

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")

    rows = _load_report()
    prog = _load_progress()
    start = prog.get("start_time", time.time())
    sims_used = prog.get("sims_used", 0)
    iteration = prog.get("iteration", 0)
    log.info(f"resume: iteration={iteration} sims_used={sims_used} "
             f"existing_rows={len(rows)}")

    while True:
        if sims_used >= args.max_sims:
            log.info(f"hit --max-sims={args.max_sims}; stopping")
            return 1
        elapsed_h = (time.time() - start) / 3600.0
        if elapsed_h >= args.max_hours:
            log.info(f"hit --max-hours={args.max_hours}; stopping")
            return 1

        iteration += 1
        seed = args.seed + iteration
        exprs = generate(args.batch, seed=seed, max_depth=args.max_depth)
        log.info(f"=== iter {iteration}: generated {len(exprs)} expressions "
                 f"(sims_used={sims_used}/{args.max_sims}, "
                 f"elapsed={elapsed_h:.2f}h/{args.max_hours}h)")
        for j, expr in enumerate(exprs, 1):
            log.info(f" --- [{j}/{len(exprs)}] {expr}")
            try:
                trials = search_one(cm.session, expr, args.trials, seed + j)
            except Exception as e:
                log.exception(f"search_one crashed: {e}")
                continue
            sims_used += len(trials)
            for r in trials:
                rows.append(asdict(r))
            _save_report(rows)
            for r in trials:
                if _is_winner(r):
                    WINNER.write_text(json.dumps({
                        "alpha_id":      r.alpha_id,
                        "expression":    r.expression,
                        "optimized":     r.optimized,
                        "settings":      r.settings,
                        "sharpe":        r.sharpe,
                        "turnover":      r.turnover,
                        "fitness":       r.fitness,
                        "returns":       r.returns,
                        "drawdown":      r.drawdown,
                        "checks_passed": r.checks_passed,
                        "checks_total":  r.checks_total,
                        "sims_used":     sims_used,
                        "iteration":     iteration,
                    }, indent=2))
                    log.info("")
                    log.info("=" * 72)
                    log.info(f"WINNER alpha_id={r.alpha_id}  "
                             f"SH={r.sharpe:+.3f} TO={r.turnover:.3f} "
                             f"FIT={r.fitness:+.3f} "
                             f"checks={r.checks_passed}/{r.checks_total}")
                    log.info(f"  expr: {r.optimized}")
                    log.info(f"  settings: {r.settings}")
                    log.info("=" * 72)
                    prog.update({"iteration": iteration,
                                 "sims_used": sims_used,
                                 "start_time": start,
                                 "winner": r.alpha_id})
                    _save_progress(prog)
                    return 0
                # Log the near-misses
                if r.ok and r.checks_passed >= max(1, r.checks_total - 2):
                    log.info(f"   near miss: {r.alpha_id} "
                             f"checks={r.checks_passed}/{r.checks_total} "
                             f"SH={r.sharpe:+.3f} TO={r.turnover:.3f} "
                             f"FIT={r.fitness:+.3f}")
            if sims_used >= args.max_sims:
                break
            elapsed_h = (time.time() - start) / 3600.0
            if elapsed_h >= args.max_hours:
                break
        prog.update({"iteration": iteration,
                     "sims_used": sims_used,
                     "start_time": start})
        _save_progress(prog)


if __name__ == "__main__":
    sys.exit(main() or 0)
