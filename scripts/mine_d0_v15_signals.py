"""D0 v15 — switch SIGNAL family while keeping trade_when news gate.

v11/v12 cluster cap: chk=6 with SH 1.58-1.61, all blocked by LOW_SHARPE.
The IV-skew (call-put) + snt_value 1st leg has a structural SH ceiling.

v15 fixes the gate+wrapper but TPE-searches the SIGNAL family:
  - iv_skew      (baseline): rank(IV_call_60 - IV_put_60)
  - iv_term      : rank(IV_mean_60 - IV_mean_30)  -- vol curve steepness
  - iv_vs_hv     : rank(IV_mean_60 - HV_60)       -- vol surprise
  - iv_mean_skew : rank(IV_mean_skew_60)          -- broker skew metric
  - pcr_oi       : rank(-pcr_oi_60)               -- put-call OI ratio
  - iv_term_30_5 : rank(IV_mean_30 - IV_call_5)   -- short curve

2nd leg:
  - snt_value
  - snt_buzz
  - none (signal alone)

Same trade_when news gate. Same neutralization/decay search.
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
log = logging.getLogger("mine-v15")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V15_RESULTS.json"
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
    "delay":          0,
    "pasteurization": "ON",
}

SIGNAL_LIBRARY = {
    "iv_skew":      "rank(implied_volatility_call_60 - implied_volatility_put_60)",
    "iv_term":      "rank(implied_volatility_mean_60 - implied_volatility_mean_30)",
    "iv_vs_hv":     "rank(implied_volatility_mean_60 - historical_volatility_60)",
    "iv_mean_skew": "rank(implied_volatility_mean_skew_60)",
    "pcr_oi":       "rank(-1 * pcr_oi_60)",
    "iv_term_30":   "rank(implied_volatility_mean_30 - implied_volatility_mean_60)",
}

LEG2_LIBRARY = {
    "snt_value": "rank(snt_value)",
    "snt_buzz":  "rank(snt_buzz)",
    "none":      None,
}


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


def build_expression(signal_name: str, leg2_name: str,
                     gate_thresh: float, w1: float, w2: float,
                     decay_n: int) -> str:
    signal = SIGNAL_LIBRARY[signal_name]
    leg2 = LEG2_LIBRARY[leg2_name]
    gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f})"
    if leg2 is None:
        body = f"ts_decay_linear({w1:.2f} * {signal}, {decay_n})"
    else:
        body = f"ts_decay_linear({w1:.2f} * {signal} + {w2:.2f} * {leg2}, {decay_n})"
    return f"trade_when({gate}, {body}, -1)"


def evaluate_pass(alpha_json: dict) -> tuple[bool, list[str]]:
    fails: list[str] = []
    isb = alpha_json.get("is") or {}
    checks = isb.get("checks") or []
    if not checks:
        return False, ["no is.checks returned"]
    for c in checks:
        name = c.get("name", "?"); result = c.get("result", "?")
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
    ap.add_argument("--seed", type=int, default=15151)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=10)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed with the v11/v12 chk=6 winning config but each signal variant
    base_seed = dict(gate_thresh=0.60, w1=1.30, w2=0.75, decay_n=35,
                     universe="TOP3000", decay=8, truncation=0.08,
                     neutralization="INDUSTRY", leg2_name="snt_value")
    for sig in SIGNAL_LIBRARY:
        s = dict(base_seed); s["signal_name"] = sig
        study.enqueue_trial(s)

    found = {"alpha_id": None}

    def objective(trial: optuna.trial.Trial) -> float:
        signal_name = trial.suggest_categorical("signal_name", list(SIGNAL_LIBRARY))
        leg2_name = trial.suggest_categorical("leg2_name", list(LEG2_LIBRARY))
        gate_thresh = trial.suggest_float("gate_thresh", 0.45, 0.85)
        w1 = trial.suggest_float("w1", 0.5, 2.5)
        w2 = trial.suggest_float("w2", 0.3, 2.0)
        decay_n = trial.suggest_int("decay_n", 5, 60)
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])
        decay = trial.suggest_categorical("decay", [4, 6, 8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY"])

        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(signal_name, leg2_name,
                                 gate_thresh, w1, w2, decay_n)
        log.info(f"t{trial.number}: sig={signal_name} leg2={leg2_name} "
                 f"gate>{gate_thresh:.2f} w={w1:.2f}/{w2:.2f} N={decay_n} | "
                 f"u={universe} dec={decay} tr={truncation} neut={neutralization[:5]}")
        res = wq_submit(session, expr, settings)
        rec = {
            "ts": time.time(), "trial": trial.number,
            "params": trial.params, "expression": expr,
            "settings": res.settings, "ok": res.ok,
            "alpha_id": res.alpha_id, "error": res.error,
            "sharpe": res.sharpe, "turnover": res.turnover,
            "fitness": res.fitness, "returns": res.returns,
            "drawdown": res.drawdown,
            "checks_passed": res.checks_passed,
            "checks_total": res.checks_total,
        }
        if res.ok:
            log.info(f"  SH={res.sharpe:+.3f} FIT={res.fitness:+.3f} "
                     f"TO={res.turnover:.3f} chk={res.checks_passed}/{res.checks_total} alpha={res.alpha_id}")
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
                        log.info("  *** PASSED — submitting ***")
                        sub_resp = attempt_submit(session, res.alpha_id)
                        rec["submit_response"] = sub_resp
                        if sub_resp.get("ok"):
                            log.info(f"  *** SUBMIT ACCEPTED: {res.alpha_id} ***")
                            found["alpha_id"] = res.alpha_id
                    else:
                        log.info(f"  fails: {fails[:3]}")
        else:
            log.info(f"  [{res.error[:120]}]")

        append_result(rec)

        if not res.ok:
            return -10.0
        if res.turnover > 0.5:
            return res.sharpe - 5.0
        check_bonus = (res.checks_passed - 4) * 0.5
        return res.sharpe + 0.1 * res.fitness + check_bonus

    def stop_when_found(study, trial):
        if found["alpha_id"]:
            study.stop()

    try:
        study.optimize(objective, n_trials=args.trials,
                        callbacks=[stop_when_found], show_progress_bar=False)
    except KeyboardInterrupt:
        return 130

    print()
    print("=" * 100)
    if found["alpha_id"]:
        print(f"SURVIVOR: {found['alpha_id']}")
        return 0
    print("NO SURVIVOR.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
