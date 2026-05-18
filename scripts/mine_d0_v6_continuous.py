"""D0 v6 — continuous-parameter Pareto search around the champion family.

v1-v5 evidence (~200 trials): the snt_value-blended IV-skew is the
winner; champion alpha 6XRd003O:
  ts_decay_linear(rank(IV_call_60 - IV_put_60) + rank(snt_value), 54)
  TOP3000 INDUSTRY decay=6 trunc=0.10 → SH=1.83 FIT=1.41 TO=0.165
  (need SH > 2.0, sub-universe > 0.79)

v5 fixed-weight seeds (1.0, 0.5, 2.0, 3.0) wastes trials in a small
discrete grid. v6 instead:

  1. ONE parametric template:
        ts_decay_linear(
          w_iv * rank(IV_call_T1 - IV_put_T2)
          + w_snt * rank(snt_value)
          + w_hv * rank(-historical_volatility_T3),
          N)
  2. Optuna NSGA-II multi-objective: maximize (SH, FIT) simultaneously.
     TO acts as a hard prune (> 0.5 → -inf).
  3. Continuous w_*, integer N, categorical tenors, plus the D0
     setting space (universe, decay, truncation, neut, pasteurization).

Stops when WQ's `is.checks` all PASS, then calls /alphas/{id}/submit.
Results appended to WQ_D0_V6_RESULTS.json after every trial.
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
log = logging.getLogger("mine-v6")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit, D0_SETTING_SPACE  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V6_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}

IV_TENORS = [30, 60, 90, 120]
HV_TENORS = [10, 20, 30, 60]
DECAY_WINDOWS = list(range(2, 61))  # N for ts_decay_linear


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
                     iv_call_t: int, iv_put_t: int, hv_t: int,
                     decay_n: int) -> str:
    legs = [
        f"({w_iv:.3f}) * rank(implied_volatility_call_{iv_call_t} - implied_volatility_put_{iv_put_t})",
        f"({w_snt:.3f}) * rank(snt_value)",
    ]
    if abs(w_hv) > 0.05:  # only include hv leg if weight is meaningful
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
    ap.add_argument("--trials", type=int, default=100,
                     help="Total Optuna trials (each = 1 WQ simulation)")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    # NSGA-II for multi-objective (SH, FIT).
    sampler = optuna.samplers.NSGAIISampler(seed=args.seed,
                                            population_size=20)
    study = optuna.create_study(
        directions=["maximize", "maximize"],  # (SH, FIT)
        sampler=sampler,
    )

    found = {"alpha_id": None}  # mutable so objective can write to it

    def objective(trial: optuna.trial.Trial):
        # Continuous weights
        w_iv = trial.suggest_float("w_iv", 0.2, 4.0)
        w_snt = trial.suggest_float("w_snt", 0.2, 4.0)
        w_hv = trial.suggest_float("w_hv", -2.0, 2.0)
        # IV tenors
        iv_call_t = trial.suggest_categorical("iv_call_t", IV_TENORS)
        iv_put_t = trial.suggest_categorical("iv_put_t", IV_TENORS)
        # HV tenor
        hv_t = trial.suggest_categorical("hv_t", HV_TENORS)
        # Decay window
        decay_n = trial.suggest_int("decay_n", 2, 60)
        # Settings
        settings = {k: trial.suggest_categorical(k, v)
                    for k, v in D0_SETTING_SPACE.items()}

        expr = build_expression(w_iv, w_snt, w_hv,
                                iv_call_t, iv_put_t, hv_t, decay_n)
        log.info(f"trial {trial.number}: w_iv={w_iv:.2f} w_snt={w_snt:.2f} "
                 f"w_hv={w_hv:+.2f} | IV {iv_call_t}-{iv_put_t} | "
                 f"HV {hv_t} | N={decay_n} | u={settings['universe']} "
                 f"neut={settings['neutralization'][:5]} tr={settings['truncation']} dec={settings['decay']}")
        log.info(f"   expr: {expr}")
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
                        log.info("   *** PASSED all is.checks — submitting ***")
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

        # Hard prune for bad turnover
        if not res.ok:
            return (-10.0, -10.0)
        if res.turnover > 0.5:
            return (res.sharpe - 5.0, res.fitness - 5.0)
        # Multi-objective: (SH, FIT)
        return (res.sharpe, res.fitness)

    def stop_when_found(study, trial):
        if found["alpha_id"]:
            study.stop()

    try:
        study.optimize(objective, n_trials=args.trials,
                        callbacks=[stop_when_found],
                        show_progress_bar=False)
    except KeyboardInterrupt:
        log.info("interrupted")
        return 130

    print()
    print("=" * 100)
    if found["alpha_id"]:
        print(f"SURVIVOR: {found['alpha_id']}")
        return 0
    print("NO SURVIVOR. Pareto front (best trials):")
    for t in study.best_trials:
        print(f"  trial {t.number}: SH={t.values[0]:+.3f} FIT={t.values[1]:+.3f}  {t.params}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
