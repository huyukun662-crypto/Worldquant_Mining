"""Mine D0 factors on WQ Brain until one passes all is.checks AND
the /alphas/{id}/submit endpoint accepts.

For each seed in `mining_pipeline.d0_seeds.SEED_EXPRESSIONS`:
  - Tune integer literals + (universe, decay, truncation, neutralization)
    via Optuna TPE.
  - After each WQ simulation, evaluate `is.checks` against the published
    submission pass bar (see PASS_BAR below).
  - On the first full-PASS candidate, POST /alphas/{id}/submit and
    record the response.

Every attempt is appended to WQ_D0_V14_RESULTS.json so progress
survives crashes / restarts.

Usage:
    python scripts/mine_d0_until_pass.py [--trials 30] [--seeds-shuffle]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path

import optuna

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mine-d0")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit, D0_SETTING_SPACE  # noqa: E402
from mining_pipeline.expressions import integer_positions, parameterize  # noqa: E402
from mining_pipeline.d0_seeds_v14 import SEED_EXPRESSIONS  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V14_RESULTS.json"

# WQ Brain's own is.checks block is the source of truth for the submit
# bar — the platform applies per-tier, per-delay thresholds (e.g. D0
# requires sharpe > 2.0, fitness > 1.3 on this account) that hard-coded
# values would drift out of sync with. We accept a candidate iff every
# is.check returns "PASS", except SELF_CORRELATION which is allowed to be
# PENDING (WQ re-runs it at submit time).
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def append_result(rec: dict) -> None:
    if RESULTS_FILE.exists():
        try:
            data = json.loads(RESULTS_FILE.read_text())
        except Exception:
            data = []
    else:
        data = []
    data.append(rec)
    RESULTS_FILE.write_text(json.dumps(data, indent=2))


def evaluate_pass(alpha_json: dict) -> tuple[bool, list[str]]:
    """Return (all_pass, failure_reasons). WQ's is.checks block carries
    the per-tier thresholds; we trust them."""
    fails: list[str] = []
    isb = alpha_json.get("is") or {}
    checks = isb.get("checks") or []
    if not checks:
        return False, ["no is.checks returned"]
    for c in checks:
        name = c.get("name", "?")
        result = c.get("result", "?")
        if result == "PASS":
            continue
        if result == "PENDING" and name in SELF_CORR_PENDING_OK:
            continue
        limit = c.get("limit"); value = c.get("value")
        fails.append(f"{name}={result} (limit={limit}, value={value})")
    return len(fails) == 0, fails


def attempt_submit(session, alpha_id: str) -> dict:
    sa_mod = _load(REPO / "scripts" / "submit_alpha.py", "sa")
    return sa_mod.submit_alpha(session, alpha_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=30,
                     help="Optuna trials per seed (each = 1 WQ simulation)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--seeds-shuffle", action="store_true",
                     help="Shuffle seed order each pass")
    ap.add_argument("--max-passes", type=int, default=10,
                     help="Max passes over the seed list before giving up")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    session = cm.session
    survivor: dict | None = None
    rnd = random.Random(args.seed)

    for pass_idx in range(args.max_passes):
        seeds = list(SEED_EXPRESSIONS)
        if args.seeds_shuffle:
            rnd.shuffle(seeds)
        log.info(f"=== pass {pass_idx + 1}/{args.max_passes} "
                 f"({len(seeds)} seeds × up to {args.trials} trials) ===")

        for seed_idx, expression in enumerate(seeds, 1):
            log.info(f"--- [{pass_idx + 1}.{seed_idx}/{len(seeds)}] seed: {expression}")
            positions = integer_positions(expression)
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            sampler = optuna.samplers.TPESampler(seed=args.seed + pass_idx * 1000 + seed_idx)
            study = optuna.create_study(direction="maximize", sampler=sampler)
            found: dict | None = None

            def objective(trial: optuna.trial.Trial) -> float:
                nonlocal found
                settings = {k: trial.suggest_categorical(k, v)
                            for k, v in D0_SETTING_SPACE.items()}
                windows = {p: trial.suggest_int(f"w{p}", 3, 60) for p in positions}
                final = parameterize(expression, windows) if windows else expression
                log.info(f"   trial {trial.number}: settings={settings} windows={windows}")
                res = wq_submit(session, final, settings)
                rec = {
                    "ts": time.time(),
                    "pass": pass_idx + 1,
                    "seed_idx": seed_idx,
                    "seed_expression": expression,
                    "optimized": final,
                    "settings": res.settings,
                    "ok": res.ok,
                    "alpha_id": res.alpha_id,
                    "error": res.error,
                    "sharpe": res.sharpe, "turnover": res.turnover,
                    "fitness": res.fitness, "returns": res.returns,
                    "drawdown": res.drawdown,
                    "checks_passed": res.checks_passed,
                    "checks_total": res.checks_total,
                }
                if res.ok:
                    log.info(f"      WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                             f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total} "
                             f"alpha_id={res.alpha_id}")
                else:
                    log.info(f"      [{res.error[:120]}]")

                # Fetch full alpha to evaluate checks ourselves
                if res.ok and res.alpha_id:
                    ra = session.get(
                        f"https://api.worldquantbrain.com/alphas/{res.alpha_id}",
                        timeout=30)
                    if ra.status_code == 200:
                        alpha_full = ra.json()
                        passed, fails = evaluate_pass(alpha_full)
                        rec["all_pass"] = passed
                        rec["failure_reasons"] = fails
                        if passed:
                            log.info("      *** PASSED all is.checks — submitting ***")
                            sub_resp = attempt_submit(session, res.alpha_id)
                            rec["submit_response"] = sub_resp
                            if sub_resp.get("ok"):
                                log.info(f"      *** SUBMIT ACCEPTED: alpha_id={res.alpha_id} ***")
                                found = rec
                            else:
                                log.warning(f"      submit POST returned {sub_resp.get('status')}")
                        else:
                            log.info(f"      fails: {fails[:3]}")

                append_result(rec)

                if found is not None:
                    trial.study.stop()
                # Optuna objective
                if not res.ok:
                    return -10.0
                score = res.sharpe
                # Reward fitness slightly so we prefer alphas with both
                score += 0.2 * (res.fitness or 0.0)
                # Penalize turnover > 0.5 (within bounds but risky)
                if res.turnover > 0.5:
                    score -= (res.turnover - 0.5) * 2.0
                return score

            try:
                study.optimize(objective, n_trials=args.trials,
                                show_progress_bar=False)
            except KeyboardInterrupt:
                log.info("interrupted by user")
                return 130

            if found is not None:
                survivor = found
                break

        if survivor is not None:
            break

    print()
    print("=" * 100)
    if survivor:
        print("SURVIVOR FOUND — submitted to WQ Brain for PENDING review")
        print(f"  alpha_id:  {survivor['alpha_id']}")
        print(f"  expression:{survivor['optimized']}")
        print(f"  settings:  {survivor['settings']}")
        print(f"  sharpe={survivor['sharpe']:.3f} fitness={survivor['fitness']:.3f} "
              f"turnover={survivor['turnover']:.3f}")
        print(f"  submit:    {survivor.get('submit_response',{}).get('status')}")
        return 0
    print("NO SURVIVOR after all passes")
    return 1


if __name__ == "__main__":
    sys.exit(main())
