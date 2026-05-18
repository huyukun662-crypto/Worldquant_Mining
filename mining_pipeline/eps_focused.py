"""Focused Optuna search around the SH=+1.17 EPS/close discovery.

Best from D0_MINING_REPORT.json:
    zscore(rank(ts_rank(divide(est_epsr, close), 9)))
    SH=+1.15  TO=0.41  FIT=+0.53  TOP1000 INDUSTRY decay=? trunc=?

Strategy: enumerate a small family of value-to-price shapes (different
numerator estimate, wrapper, and time-series transform) and let Optuna
search the joint (window, settings) space for ~30 sims.

Run:
    python -m mining_pipeline.eps_focused --trials 30
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

import optuna

from .wq_pipeline import submit, FIXED_SETTINGS

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eps-focused")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# Candidate numerators (verified present at delay=0 TOP1000) and
# denominators that form value/scale ratios.
NUMERATORS = ("est_epsr", "est_ebit", "est_netprofit", "est_cashflow_op",
              "est_tot_assets")
DENOMINATORS = ("close", "cap", "vwap")

# Shape templates — all are pattern-shaped value/price factors with a
# single integer window {D} that Optuna refines.
SHAPES = (
    "{wrap}(rank(ts_rank(divide({num}, {den}), {D})))",
    "{wrap}(ts_rank(divide({num}, {den}), {D}))",
    "{wrap}(ts_zscore(divide({num}, {den}), {D}))",
    "{wrap}(rank(ts_mean(divide({num}, {den}), {D})))",
    "{wrap}(ts_decay_linear(rank(divide({num}, {den})), {D}))",
    "{wrap}(rank(ts_delta(divide({num}, {den}), {D})))",
)
WRAPPERS = ("zscore", "rank", "scale", "normalize")

# D0-tier settings space (compatible with this account, no D1, no
# tier-gated ops).
SETTINGS = {
    "universe":       ["TOP1000", "TOP500"],
    "delay":          [0],
    "decay":          [0, 1, 2, 4, 8, 16],
    "truncation":     [0.05, 0.08, 0.10],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR"],
    "pasteurization": ["ON"],
}

REPORT = REPO / "D0_EPS_REPORT.json"
WINNER = REPO / "D0_EPS_WINNER.json"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=30,
                    help="Optuna trials = WQ simulations")
    ap.add_argument("--seed",   type=int, default=71)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    rows: list[dict] = json.loads(REPORT.read_text()) if REPORT.exists() else []
    start = time.time()

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    winner_alpha = {"alpha_id": ""}

    def objective(trial: optuna.trial.Trial) -> float:
        shape = trial.suggest_categorical("shape", list(range(len(SHAPES))))
        wrap  = trial.suggest_categorical("wrap",  WRAPPERS)
        num   = trial.suggest_categorical("num",   NUMERATORS)
        den   = trial.suggest_categorical("den",   DENOMINATORS)
        D     = trial.suggest_int("D", 3, 30)
        sset  = {k: trial.suggest_categorical(k, v) for k, v in SETTINGS.items()}
        expr  = SHAPES[shape].format(wrap=wrap, num=num, den=den, D=D)
        log.info(f" --- trial: {expr}  settings={sset}")
        res = submit(cm.session, expr, sset)
        rows.append(asdict(res))
        REPORT.write_text(json.dumps(rows, indent=2))
        if not res.ok:
            log.info(f"      [{res.error[:80]}]")
            return -100.0
        fraction = res.checks_passed / max(res.checks_total, 1)
        score = res.sharpe + 10.0 * fraction
        if res.turnover >= 0.70:
            score -= 5.0
        log.info(f"      WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                 f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total}"
                 f" score={score:+.3f}")
        if res.ok and res.checks_total > 0 and res.checks_passed == res.checks_total:
            WINNER.write_text(json.dumps({
                "alpha_id":      res.alpha_id,
                "expression":    expr,
                "settings":      res.settings,
                "sharpe":        res.sharpe,
                "turnover":      res.turnover,
                "fitness":       res.fitness,
                "returns":       res.returns,
                "checks_passed": res.checks_passed,
                "checks_total":  res.checks_total,
            }, indent=2))
            winner_alpha["alpha_id"] = res.alpha_id
            study.stop()
        return score

    study.optimize(objective, n_trials=args.trials, show_progress_bar=False)

    elapsed = (time.time() - start) / 60
    sims = sum(1 for r in rows if r.get("ok") or r.get("error"))
    print()
    print("=" * 78)
    if winner_alpha["alpha_id"]:
        print(f"WINNER alpha_id={winner_alpha['alpha_id']}  "
              f"({sims} sims, {elapsed:.1f} min)")
    else:
        ok = [r for r in rows if r.get("ok")]
        if ok:
            top = sorted(ok, key=lambda r: -r.get("sharpe", 0))[:3]
            print(f"no submit-eligible winner in {args.trials} trials "
                  f"({sims} sims, {elapsed:.1f} min)")
            print("top 3 by SH:")
            for r in top:
                print(f"  {r['alpha_id']:10}  SH={r['sharpe']:+.3f}  "
                      f"TO={r['turnover']:.3f}  FIT={r['fitness']:+.3f}  "
                      f"checks={r['checks_passed']}/{r['checks_total']}  "
                      f"{r['optimized'][:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
