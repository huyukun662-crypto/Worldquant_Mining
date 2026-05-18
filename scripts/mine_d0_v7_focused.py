"""D0 v7 — focused TPE search seeded with champion alpha 6XRd003O.

v6 NSGA-II with 7 free continuous params didn't converge in 23 trials
(top SH=0.82 vs known 1.83). v7 narrows the search:

  - FIX known winners: TOP3000, INDUSTRY, pasteur=ON, IV=60-60.
  - TUNE: w_iv, w_snt, w_hv (continuous), hv_t (cat), N (int),
          decay (int), truncation (cat).
  - SEED Optuna TPE with the champion params via study.enqueue_trial
    so the first 3-4 trials replay/perturb the known good point.

Template:
  ts_decay_linear(
    w_iv * rank(IV_call_60 - IV_put_60)
    + w_snt * rank(snt_value)
    + w_hv * rank(-historical_volatility_T),
    N)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

import optuna

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mine-v7")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V7_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
    "universe":       "TOP3000",
    "delay":          0,
    "neutralization": "INDUSTRY",
    "pasteurization": "ON",
}

HV_TENORS = [10, 20, 30, 60]


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


def build_expression(w_iv: float, w_snt: float, w_hv: float,
                     hv_t: int, decay_n: int) -> str:
    legs = [
        f"({w_iv:.3f}) * rank(implied_volatility_call_60 - implied_volatility_put_60)",
        f"({w_snt:.3f}) * rank(snt_value)",
    ]
    if abs(w_hv) > 0.05:
        legs.append(f"({w_hv:.3f}) * rank(-historical_volatility_{hv_t})")
    body = " + ".join(legs)
    return f"ts_decay_linear({body}, {decay_n})"


def evaluate_pass(alpha_json: dict) -> tuple[bool, list[str]]:
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
    ap.add_argument("--trials", type=int, default=80)
    ap.add_argument("--seed", type=int, default=7777)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=5)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed with known-good points (champion + nearby perturbations)
    seed_trials = [
        # Exact champion (6XRd003O: SH=1.83 FIT=1.41 in v4)
        {"w_iv": 1.0, "w_snt": 1.0, "w_hv": 0.0, "hv_t": 10, "decay_n": 54,
         "decay": 6, "truncation": 0.10},
        # Champion with shorter N
        {"w_iv": 1.0, "w_snt": 1.0, "w_hv": 0.0, "hv_t": 10, "decay_n": 30,
         "decay": 6, "truncation": 0.08},
        # Champion with longer N
        {"w_iv": 1.0, "w_snt": 1.0, "w_hv": 0.0, "hv_t": 10, "decay_n": 60,
         "decay": 8, "truncation": 0.08},
        # Champion + small HV leg
        {"w_iv": 1.0, "w_snt": 1.0, "w_hv": 0.3, "hv_t": 20, "decay_n": 50,
         "decay": 6, "truncation": 0.08},
        # Champion + IV-heavy
        {"w_iv": 1.5, "w_snt": 0.8, "w_hv": 0.0, "hv_t": 10, "decay_n": 50,
         "decay": 6, "truncation": 0.08},
        # Champion + snt-heavy
        {"w_iv": 0.8, "w_snt": 1.5, "w_hv": 0.0, "hv_t": 10, "decay_n": 50,
         "decay": 6, "truncation": 0.08},
    ]
    for st in seed_trials:
        study.enqueue_trial(st)

    found = {"alpha_id": None}

    def objective(trial: optuna.trial.Trial) -> float:
        w_iv = trial.suggest_float("w_iv", 0.3, 3.0)
        w_snt = trial.suggest_float("w_snt", 0.3, 3.0)
        w_hv = trial.suggest_float("w_hv", -1.0, 1.0)
        hv_t = trial.suggest_categorical("hv_t", HV_TENORS)
        decay_n = trial.suggest_int("decay_n", 5, 60)
        decay = trial.suggest_categorical("decay", [4, 6, 8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])

        settings = dict(FIXED_SETTINGS)
        settings["decay"] = decay
        settings["truncation"] = truncation

        expr = build_expression(w_iv, w_snt, w_hv, hv_t, decay_n)
        log.info(f"trial {trial.number}: w_iv={w_iv:.2f} w_snt={w_snt:.2f} "
                 f"w_hv={w_hv:+.2f} HV={hv_t} N={decay_n} dec={decay} tr={truncation}")
        res = wq_submit(session, expr, settings)

        rec = {
            "ts": time.time(),
            "trial": trial.number,
            "params": trial.params,
            "expression": expr,
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
            log.info(f"   SH={res.sharpe:+.3f} FIT={res.fitness:+.3f} "
                     f"TO={res.turnover:.3f} checks={res.checks_passed}/{res.checks_total} alpha={res.alpha_id}")
            if res.alpha_id:
                ra = session.get(
                    f"https://api.worldquantbrain.com/alphas/{res.alpha_id}",
                    timeout=30)
                if ra.status_code == 200:
                    alpha_full = ra.json()
                    passed, fails = evaluate_pass(alpha_full)
                    rec["all_pass"] = passed
                    rec["failure_reasons"] = fails
                    if passed:
                        log.info("   *** PASSED is.checks — submitting ***")
                        sub_resp = attempt_submit(session, res.alpha_id)
                        rec["submit_response"] = sub_resp
                        if sub_resp.get("ok"):
                            log.info(f"   *** SUBMIT ACCEPTED: {res.alpha_id} ***")
                            found["alpha_id"] = res.alpha_id
                    else:
                        log.info(f"   fails: {fails[:3]}")
        else:
            log.info(f"   [{res.error[:120]}]")

        append_result(rec)

        if not res.ok:
            return -10.0
        if res.turnover > 0.5:
            return res.sharpe - 5.0
        # Single-objective: SH, with small FIT bonus to nudge toward
        # high-FIT alphas (which also benefit sub-universe SH)
        return res.sharpe + 0.1 * res.fitness

    def stop_when_found(study, trial):
        if found["alpha_id"]:
            study.stop()

    try:
        study.optimize(objective, n_trials=args.trials,
                        callbacks=[stop_when_found],
                        show_progress_bar=False)
    except KeyboardInterrupt:
        return 130

    print()
    print("=" * 100)
    if found["alpha_id"]:
        print(f"SURVIVOR: {found['alpha_id']}")
        return 0
    print("NO SURVIVOR. Best trial:")
    bt = study.best_trial
    print(f"  trial {bt.number}: value={bt.value:.3f} params={bt.params}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
