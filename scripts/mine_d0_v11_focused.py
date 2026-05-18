"""D0 v11 — focused TPE on the v10 trade_when+IV+snt breakthrough.

v10 trial 1 (alpha vR5Yqr0b) PASSED both CONCENTRATED_WEIGHT and
LOW_SUB_UNIVERSE_SHARPE for the first time:
  trade_when((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > 0.8),
             ts_decay_linear(rank(IV_skew) + rank(snt_value), 41), -1)
  TOP1000 / dec=4 / tr=0.05 / INDUSTRY → SH=0.65 FIT=0.36 TO=0.057 (chk=5/8)

Only blockers now are LOW_SHARPE and LOW_FITNESS. The structural fails
are gone. v11 tunes the parameters tightly to push SH past 2.0 while
keeping CW+SUB pass:

  - FIX expression: trade_when(NEWS_GATE, IV+snt blend, -1)
  - TUNE: gate threshold (continuous 0.5-0.95), N (3-60), w_iv, w_snt
          (continuous 0.5-2.5), settings (TOP1000/3000, decay, trunc, neut)
  - SEED with v10 known-good points

Optuna TPE single-objective: maximize SH * (1 + 0.1*FIT) — bias toward
both SH and FIT.
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
log = logging.getLogger("mine-v11")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V11_RESULTS.json"
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


def build_expression(gate_kind: str, gate_thresh: float,
                     w_iv: float, w_snt: float, decay_n: int) -> str:
    # gate_kind in {'and', 'or', 'or_loose'}
    if gate_kind == "and":
        gate = f"((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f}))"
    elif gate_kind == "or":
        gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f})"
    elif gate_kind == "or_loose":
        gate = f"(ts_rank(abs(news_pct_90min), 60) > {gate_thresh:.2f})"
    else:
        raise ValueError(gate_kind)
    body = (f"ts_decay_linear({w_iv:.2f} * rank(implied_volatility_call_60 - implied_volatility_put_60) "
            f"+ {w_snt:.2f} * rank(snt_value), {decay_n})")
    return f"trade_when({gate}, {body}, -1)"


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
    ap.add_argument("--seed", type=int, default=11111)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=8)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed with known-good v10 vR5Yqr0b: TOP1000, dec=4, tr=0.05, INDUSTRY,
    # AND gate 0.8, w_iv=1.0, w_snt=1.0, N=41
    seed_trials = [
        # vR5Yqr0b exact replay
        {"gate_kind": "and", "gate_thresh": 0.8, "w_iv": 1.0, "w_snt": 1.0,
         "decay_n": 41, "universe": "TOP1000", "decay": 4, "truncation": 0.05,
         "neutralization": "INDUSTRY"},
        # Same but TOP3000 (higher SH potential)
        {"gate_kind": "and", "gate_thresh": 0.8, "w_iv": 1.0, "w_snt": 1.0,
         "decay_n": 41, "universe": "TOP3000", "decay": 4, "truncation": 0.05,
         "neutralization": "INDUSTRY"},
        # Looser gate + TOP3000
        {"gate_kind": "or", "gate_thresh": 0.6, "w_iv": 1.0, "w_snt": 1.0,
         "decay_n": 30, "universe": "TOP3000", "decay": 6, "truncation": 0.08,
         "neutralization": "INDUSTRY"},
        # IV-heavy + AND gate + TOP3000
        {"gate_kind": "and", "gate_thresh": 0.7, "w_iv": 1.5, "w_snt": 0.8,
         "decay_n": 20, "universe": "TOP3000", "decay": 4, "truncation": 0.05,
         "neutralization": "INDUSTRY"},
    ]
    for st in seed_trials:
        study.enqueue_trial(st)

    found = {"alpha_id": None}

    def objective(trial: optuna.trial.Trial) -> float:
        gate_kind = trial.suggest_categorical("gate_kind", ["and", "or", "or_loose"])
        gate_thresh = trial.suggest_float("gate_thresh", 0.5, 0.95)
        w_iv = trial.suggest_float("w_iv", 0.5, 2.5)
        w_snt = trial.suggest_float("w_snt", 0.5, 2.5)
        decay_n = trial.suggest_int("decay_n", 3, 60)
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])
        decay = trial.suggest_categorical("decay", [2, 4, 6, 8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY"])

        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(gate_kind, gate_thresh, w_iv, w_snt, decay_n)
        log.info(f"t{trial.number}: gate={gate_kind}>{gate_thresh:.2f} w={w_iv:.2f}/{w_snt:.2f} "
                 f"N={decay_n} | u={universe} dec={decay} tr={truncation} neut={neutralization[:5]}")
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
        # Reward SH but boost trials that pass more checks
        check_bonus = (res.checks_passed - 4) * 0.5  # +0.5 for each check above 4
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
    print("NO SURVIVOR. Best trial:")
    bt = study.best_trial
    print(f"  trial {bt.number}: value={bt.value:.3f} params={bt.params}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
