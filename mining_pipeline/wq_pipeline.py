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

from .expressions import generate, integer_positions, parameterize, reload_pool

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wq-pipeline")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


# Setting search space — per user spec, ALL settings tunable so the
# optimizer can find any combination that satisfies SH>1.25, TO<0.25,
# FIT>1. Expressions themselves stay free to mutate (no template reuse).
# Account-imposed limits: delay must be 1 (no delay-0 access on this tier).
SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000", "TOP500", "TOP200"],
    "delay":          [1],
    "decay":          [0, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128],
    "truncation":     [0.0, 0.01, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20],
    "neutralization": ["NONE", "MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"],
    "pasteurization": ["ON", "OFF"],
    "nanHandling":    ["OFF", "ON"],
    "testPeriod":     ["P0Y0M", "P1Y0M", "P2Y0M", "P3Y0M"],
}

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",  # account allows only VERIFY
    "visualization":  False,
    "maxTrade":       "OFF",
}

# User filter: WQ Brain's official thresholds
SHARPE_FLOOR = 1.25
TURNOVER_CEILING = 0.25
FITNESS_FLOOR = 1.0


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


BLACKLIST_PATH = REPO / "constants" / "field_blacklist.json"


def _load_blacklist() -> set[str]:
    if BLACKLIST_PATH.exists():
        return set(json.loads(BLACKLIST_PATH.read_text()))
    return set()


def _add_blacklist(field: str) -> None:
    bl = _load_blacklist()
    bl.add(field)
    BLACKLIST_PATH.write_text(json.dumps(sorted(bl), indent=2))


import re
_INVALID_FIELD_RE = re.compile(r"Invalid data field (\S+?)\.")
_UNIT_MISMATCH_RE = re.compile(r"Incompatible unit")


def search_one(session, expression: str, n_trials: int, seed: int) -> list[WQResult]:
    """Run optuna trials over (expression-windows, sim-settings) for one
    base expression. Returns ALL trial results (not just the best).

    Early-stops the Optuna study if the expression references a field WQ
    rejects as "Invalid data field" — no setting change can fix that, so
    the remaining trials would be pure waste. The bad field is added to
    a persistent blacklist that the generator excludes in future batches.
    """
    positions = integer_positions(expression)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    trials_log: list[WQResult] = []
    bad_field = {"name": None}

    def objective(trial: optuna.trial.Trial) -> float:
        settings = {k: trial.suggest_categorical(k, v) for k, v in SETTING_SPACE.items()}
        windows = {p: trial.suggest_int(f"w{p}", 3, 60) for p in positions}
        final = parameterize(expression, windows) if windows else expression
        log.info(f"   trial: settings={settings} windows={windows}")
        res = submit(session, final, settings)
        res.optimized = final
        trials_log.append(res)
        if not res.ok:
            log.info(f"      [{res.error[:80]}]")
            m = _INVALID_FIELD_RE.search(res.error)
            if m:
                bad_field["name"] = m.group(1)
                _add_blacklist(m.group(1))
                log.info(f"      blacklisting field '{m.group(1)}'; "
                         f"aborting remaining trials for this expression")
                study.stop()
            elif _UNIT_MISMATCH_RE.search(res.error):
                # Unit mismatch is a property of the expression itself, not
                # the settings. No trial can rescue it; abort and move on.
                log.info(f"      expression has incompatible units; "
                         f"aborting remaining trials")
                study.stop()
            return -10.0
        penalty = 0.0
        if res.turnover >= TURNOVER_CEILING:
            penalty += 5.0
        if res.fitness < FITNESS_FLOOR:
            penalty += 5.0
        score = res.sharpe - penalty
        log.info(f"      WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                 f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total}")
        return score

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return trials_log


def _survivors(results: list[WQResult]) -> list[WQResult]:
    s = [r for r in results if r.ok and r.sharpe > SHARPE_FLOOR
         and r.turnover < TURNOVER_CEILING and r.fitness > FITNESS_FLOOR]
    s.sort(key=lambda r: r.sharpe, reverse=True)
    return s


def _emit_milestone(round_idx: int, survivors: list[WQResult],
                    milestones_dir: Path) -> None:
    """Emit a Chinese-language milestone report for round_idx (which is the
    1-indexed bucket of 5 survivors). Writes both stdout and a per-round
    JSON file under MILESTONES/round_{n}.json so prior rounds are durable."""
    milestones_dir.mkdir(exist_ok=True)
    bucket = survivors[(round_idx - 1) * 5 : round_idx * 5]
    out_path = milestones_dir / f"round_{round_idx:02d}.json"
    out_path.write_text(json.dumps([asdict(r) for r in bucket], indent=2))

    print()
    print("=" * 110)
    print(f"【第 {round_idx} 轮】产出 5 个符合标准的因子 "
          f"(SH>{SHARPE_FLOOR} 且 TO<{TURNOVER_CEILING} 且 FIT>{FITNESS_FLOOR})")
    print("=" * 110)
    for i, r in enumerate(bucket, 1):
        s = r.settings
        print(f"\n  因子 {i}: alpha_id = {r.alpha_id}")
        print(f"    表达式: {r.optimized}")
        print(f"    WQ Brain 回测: Sharpe={r.sharpe:+.3f}  Turnover={r.turnover:.3f}  "
              f"Fitness={r.fitness:+.3f}  Returns={r.returns:+.4f}  "
              f"Drawdown={r.drawdown:.4f}")
        print(f"    Checks: {r.checks_passed}/{r.checks_total} 通过")
        print(f"    Settings: universe={s.get('universe')}  delay={s.get('delay')}  "
              f"decay={s.get('decay')}  truncation={s.get('truncation')}")
        print(f"              neutralization={s.get('neutralization')}  "
              f"pasteurization={s.get('pasteurization')}  "
              f"nanHandling={s.get('nanHandling')}  testPeriod={s.get('testPeriod')}")
    print("=" * 110)
    print(f"  本轮明细已写入: {out_path.relative_to(REPO)}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-exprs", type=int, default=5,
                     help="Expressions per mining batch (mined fresh each batch)")
    ap.add_argument("--trials", type=int, default=6,
                     help="Optuna trials per expression (each is one WQ simulation)")
    ap.add_argument("--seed", type=int, default=37)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--batches", type=int, default=40,
                     help="Maximum mining batches before stopping unconditionally")
    ap.add_argument("--target-rounds", type=int, default=4,
                     help="Stop after producing this many milestone rounds (each = 5 survivors)")
    ap.add_argument("--out", type=str, default="WQ_MINING_REPORT.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    sims_per_batch = args.n_exprs * args.trials
    log.info(f"iterating up to {args.batches} batches × {args.n_exprs} fresh "
             f"expressions × {args.trials} trials = up to "
             f"{args.batches * sims_per_batch} WQ simulations")
    log.info(f"each batch mines from a 150-field pool spanning analyst, "
             f"fundamental, model, news, option, pv, sentiment, socialmedia")
    log.info(f"survivor gate: SH>{SHARPE_FLOOR} AND TO<{TURNOVER_CEILING} "
             f"AND FIT>{FITNESS_FLOOR}")
    log.info(f"will emit a milestone (round-of-5) every 5 cumulative survivors; "
             f"target {args.target_rounds} milestones")

    milestones_dir = REPO / "MILESTONES"
    all_results: list[WQResult] = []
    seen_exprs: set[str] = set()
    emitted_rounds = 0

    for batch_idx in range(1, args.batches + 1):
        batch_seed = args.seed + batch_idx * 1000
        # Reload pool minus newly-blacklisted fields from prior batches
        n_fields, n_cats = reload_pool()
        log.info("")
        log.info(f"############## BATCH {batch_idx}/{args.batches} "
                 f"(seed={batch_seed}, pool={n_fields} fields / "
                 f"{n_cats} categories) ##############")
        round_exprs: list[str] = []
        attempt = 0
        while len(round_exprs) < args.n_exprs and attempt < 50:
            attempt += 1
            cand = generate(args.n_exprs * 2, seed=batch_seed + attempt,
                            max_depth=args.max_depth)
            for e in cand:
                if e in seen_exprs:
                    continue
                round_exprs.append(e); seen_exprs.add(e)
                if len(round_exprs) >= args.n_exprs:
                    break
        log.info(f"batch {batch_idx}: {len(round_exprs)} fresh expressions")
        for e in round_exprs:
            log.info(f"   {e}")

        for i, expr in enumerate(round_exprs, 1):
            log.info(f"=== B{batch_idx} [{i}/{len(round_exprs)}] expression: {expr}")
            res_list = search_one(cm.session, expr, args.trials, batch_seed + i)
            all_results.extend(res_list)
            with open(args.out, "w") as f:
                json.dump([asdict(r) for r in all_results], f, indent=2)

            # Check for milestone after every expression
            survivors = _survivors(all_results)
            while len(survivors) >= (emitted_rounds + 1) * 5:
                emitted_rounds += 1
                _emit_milestone(emitted_rounds, survivors, milestones_dir)
                log.info(f"### MILESTONE {emitted_rounds} REACHED "
                         f"(cumulative survivors={len(survivors)}) ###")

        if emitted_rounds >= args.target_rounds:
            log.info(f"target of {args.target_rounds} milestones reached; stopping")
            break

    survivors = _survivors(all_results)
    print()
    print("=" * 110)
    print(f"挖矿结束:  共完成 {batch_idx} 批次, {sum(1 for r in all_results if r.ok)}"
          f"/{len(all_results)} 次模拟成功, 累计 {len(survivors)} 个合格因子, "
          f"产出 {emitted_rounds} 轮报告")
    print("=" * 110)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
