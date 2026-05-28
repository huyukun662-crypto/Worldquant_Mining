"""WQ-as-evaluator mining pipeline.

Per CLAUDE.md, the local yfinance backtest is a fast triage proxy whose
numbers DO NOT generalize. The authoritative backtest is WorldQuant
Brain's `/simulations` endpoint. This module:

    1. Generates N expressions (operators × PV fields, no Alpha101 reuse).
    2. For each, runs Optuna over the JOINT search space of:
        - expression integer literals (lookback windows)
        - simulation settings: universe, delay, decay, truncation,
                                neutralization, pasteurization
       Each Optuna trial submits one simulation to WQ Brain via
       `scripts/submit_alpha.py`'s machinery and uses the WQ-returned
       IS Sharpe as the objective (with turnover-cap penalty).
    3. Reports the best (expression, settings, WQ_SH, WQ_TO, WQ_FIT,
       checks-pass-count) per expression, ranked by WQ_SH.

Run:
    python -m mining_pipeline.wq_pipeline --n-exprs 5 --trials 10
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import math
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import optuna

from .expressions import generate, integer_positions, parameterize

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wq-pipeline")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


# Setting search space - per user note: "delay decay truncation universe
# 中性化等是可以调的". Expressions themselves stay free to mutate (no
# template reuse).
SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000", "TOP500", "TOP200"],
    "delay":          [1],  # this account has no delay-0 access
    "decay":          [0, 4, 8, 16, 32, 64],
    "truncation":     [0.01, 0.05, 0.08, 0.10],
    "neutralization": ["NONE", "MARKET", "INDUSTRY", "SUBINDUSTRY", "SECTOR"],
    "pasteurization": ["ON", "OFF"],
}

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
}

# User filter: WQ Brain's official thresholds
SHARPE_FLOOR = 1.25
TURNOVER_CEILING = 0.25


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class WQResult:
    ok: bool
    expression: str
    optimized: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    alpha_id: str = ""
    error: str = ""


def submit(session, expression: str, settings: dict,
           poll_timeout_s: int = 600, poll_interval_s: int = 5) -> WQResult:
    """Submit one (expression, settings) to WQ Brain. Returns WQResult."""
    full_settings = dict(FIXED_SETTINGS)
    full_settings.update(settings)
    body = {"type": "REGULAR", "settings": full_settings, "regular": expression}

    # POST with 429 backoff
    for attempt in range(5):
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait)
            continue
        break
    if r.status_code != 201:
        return WQResult(ok=False, expression=expression, optimized=expression,
                        settings=full_settings,
                        error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return WQResult(ok=False, expression=expression, optimized=expression,
                        settings=full_settings, error="no Location header")

    # Poll
    t0 = time.time()
    while time.time() - t0 < poll_timeout_s:
        time.sleep(poll_interval_s)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st == "COMPLETE":
            alpha_id = data.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                              timeout=30)
            if ra.status_code != 200:
                return WQResult(ok=False, expression=expression,
                                optimized=expression, settings=full_settings,
                                alpha_id=alpha_id or "",
                                error=f"alpha-get-{ra.status_code}")
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            return WQResult(
                ok=True,
                expression=expression,
                optimized=expression,
                settings=full_settings,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                longCount=int(isb.get("longCount") or 0),
                shortCount=int(isb.get("shortCount") or 0),
                checks_passed=sum(1 for c in checks if c.get("result") == "PASS"),
                checks_total=len(checks),
                alpha_id=alpha_id or "",
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return WQResult(ok=False, expression=expression,
                            optimized=expression, settings=full_settings,
                            error=f"sim-{st}: {data.get('message','')[:300]}")
    return WQResult(ok=False, expression=expression, optimized=expression,
                    settings=full_settings, error="poll-timeout")


def search_one(session, expression: str, n_trials: int, seed: int) -> list[WQResult]:
    """Run optuna trials over (expression-windows, sim-settings) for one
    base expression. Returns ALL trial results (not just the best)."""
    positions = integer_positions(expression)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    trials_log: list[WQResult] = []

    def objective(trial: optuna.trial.Trial) -> float:
        # Setting choices
        settings = {k: trial.suggest_categorical(k, v) for k, v in SETTING_SPACE.items()}
        # Expression windows
        windows = {p: trial.suggest_int(f"w{p}", 3, 60) for p in positions}
        final = parameterize(expression, windows) if windows else expression
        log.info(f"   trial: settings={settings} windows={windows}")
        res = submit(session, final, settings)
        res.optimized = final
        trials_log.append(res)
        if not res.ok:
            log.info(f"      [{res.error[:80]}]")
            return -10.0
        # Penalty if turnover violates user cap
        score = res.sharpe - (5.0 if res.turnover >= TURNOVER_CEILING else 0.0)
        log.info(f"      WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                 f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total}")
        return score

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return trials_log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-exprs", type=int, default=5,
                     help="Number of base expressions to mine")
    ap.add_argument("--trials", type=int, default=8,
                     help="Optuna trials per expression (each is one WQ simulation)")
    ap.add_argument("--seed", type=int, default=37)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--out", type=str, default="WQ_MINING_REPORT.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    log.info(f"generating {args.n_exprs} expressions (no Alpha101 / classical reuse)")
    exprs = generate(args.n_exprs, seed=args.seed, max_depth=args.max_depth)
    for e in exprs: log.info(f"   {e}")

    total_trials = args.n_exprs * args.trials
    log.info(f"will run {total_trials} simulations on WQ Brain "
             f"(~{total_trials * 100 / 60:.0f} min at ~100s/sim)")

    all_results: list[WQResult] = []
    for i, expr in enumerate(exprs, 1):
        log.info(f"=== [{i}/{len(exprs)}] expression: {expr}")
        res_list = search_one(cm.session, expr, args.trials, args.seed + i)
        all_results.extend(res_list)
        # Save partial after each expression so a crash mid-run preserves data
        with open(args.out, "w") as f:
            json.dump([asdict(r) for r in all_results], f, indent=2)

    # Filter and rank
    survivors = [r for r in all_results if r.ok and r.sharpe > SHARPE_FLOOR
                  and r.turnover < TURNOVER_CEILING]
    survivors.sort(key=lambda r: r.sharpe, reverse=True)

    print()
    print("=" * 110)
    print(f"All trials: {sum(1 for r in all_results if r.ok)}/{len(all_results)} OK")
    print(f"Survivors  (WQ_SH > {SHARPE_FLOOR} AND TO < {TURNOVER_CEILING}): "
          f"{len(survivors)}")
    print()
    print(f"{'WQ_SH':>7}{'TO':>7}{'FIT':>7}{'checks':>9}  alpha_id   universe   delay  neut  expression")
    for r in survivors[:25]:
        s = r.settings
        print(f"{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}"
              f" {r.checks_passed}/{r.checks_total:<5}  "
              f"{r.alpha_id:<10} {s.get('universe'):<10} {s.get('delay')!s:<5} "
              f"{s.get('neutralization'):<13} {r.optimized[:80]}")
    print("=" * 110)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
