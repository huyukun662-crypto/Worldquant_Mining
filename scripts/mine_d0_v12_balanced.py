"""D0 v12 — force mid-range WQ decay (4-8) to balance SH vs SUB.

v11 chk=5 cluster shows a hard SH-vs-SUB tension:
  - dec=2:  SH 1.69-1.87, SUB 0.48-0.55 (FAIL)
  - dec=10: SH 1.51-1.55, SUB 0.78+ (PASS), FIT 1.06-1.28
  - dec=4-8 underexplored

v12 fixes WQ-side decay to {4, 6, 8} and tunes everything else, hoping
the mid-range smoothing keeps SUB high enough while preserving SH.

Also tries:
  - SUBINDUSTRY neutralization (finer than INDUSTRY may help SUB)
  - Explicit group_zscore wrap around the trade_when
  - Shorter HV leg (small w_hv) which v7b found boosts SUB
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
log = logging.getLogger("mine-v12")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V12_RESULTS.json"
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
                     w_iv: float, w_snt: float, w_hv: float,
                     hv_t: int, decay_n: int, wrap_group_zscore: bool) -> str:
    if gate_kind == "and":
        gate = f"((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f}))"
    elif gate_kind == "or":
        gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f})"
    else:  # or_loose
        gate = f"(ts_rank(abs(news_pct_90min), 60) > {gate_thresh:.2f})"

    legs = [
        f"{w_iv:.2f} * rank(implied_volatility_call_60 - implied_volatility_put_60)",
        f"{w_snt:.2f} * rank(snt_value)",
    ]
    if abs(w_hv) > 0.05:
        legs.append(f"{w_hv:.2f} * rank(-historical_volatility_{hv_t})")
    inner = f"ts_decay_linear({' + '.join(legs)}, {decay_n})"

    expr = f"trade_when({gate}, {inner}, -1)"
    if wrap_group_zscore:
        expr = f"group_zscore({expr}, subindustry)"
    return expr


def evaluate_pass(alpha_json: dict) -> tuple[bool, list[str]]:
    fails: list[str] = []
    isb = alpha_json.get("is") or {}
    for c in isb.get("checks") or []:
        name = c.get("name", "?")
        result = c.get("result", "?")
        if result == "PASS": continue
        if result == "PENDING" and name in SELF_CORR_PENDING_OK: continue
        fails.append(f"{name}={result} (limit={c.get('limit')}, value={c.get('value')})")
    return len(fails) == 0, fails


def attempt_submit(session, alpha_id: str) -> dict:
    sa_mod = _load(REPO / "scripts" / "submit_alpha.py", "sa")
    return sa_mod.submit_alpha(session, alpha_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=80)
    ap.add_argument("--seed", type=int, default=12121)
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

    # Seed with mid-dec variants
    for st in [
        # Jjn3YZdx (SH 1.55 SUB pass) at dec=10 → try dec=6
        {"gate_kind": "or", "gate_thresh": 0.79, "w_iv": 1.95, "w_snt": 0.70,
         "w_hv": 0.0, "hv_t": 10, "decay_n": 49, "universe": "TOP3000",
         "decay": 6, "truncation": 0.10, "neutralization": "INDUSTRY",
         "wrap_group_zscore": False},
        # wp5NLLrQ (SH 1.87 SUB fail) at dec=2 → try dec=6
        {"gate_kind": "or_loose", "gate_thresh": 0.78, "w_iv": 2.20, "w_snt": 1.30,
         "w_hv": 0.0, "hv_t": 10, "decay_n": 37, "universe": "TOP3000",
         "decay": 6, "truncation": 0.10, "neutralization": "INDUSTRY",
         "wrap_group_zscore": False},
        # group_zscore wrapped version
        {"gate_kind": "or", "gate_thresh": 0.79, "w_iv": 1.95, "w_snt": 0.70,
         "w_hv": 0.0, "hv_t": 10, "decay_n": 49, "universe": "TOP3000",
         "decay": 6, "truncation": 0.10, "neutralization": "INDUSTRY",
         "wrap_group_zscore": True},
        # SUBINDUSTRY neut with mid-dec
        {"gate_kind": "or", "gate_thresh": 0.79, "w_iv": 1.95, "w_snt": 0.70,
         "w_hv": 0.0, "hv_t": 10, "decay_n": 49, "universe": "TOP3000",
         "decay": 6, "truncation": 0.10, "neutralization": "SUBINDUSTRY",
         "wrap_group_zscore": False},
        # Small HV leg + mid-dec
        {"gate_kind": "or", "gate_thresh": 0.79, "w_iv": 1.95, "w_snt": 0.70,
         "w_hv": 0.07, "hv_t": 10, "decay_n": 49, "universe": "TOP3000",
         "decay": 6, "truncation": 0.10, "neutralization": "INDUSTRY",
         "wrap_group_zscore": False},
    ]:
        study.enqueue_trial(st)

    found = {"alpha_id": None}

    def objective(trial: optuna.trial.Trial) -> float:
        gate_kind = trial.suggest_categorical("gate_kind", ["and", "or", "or_loose"])
        gate_thresh = trial.suggest_float("gate_thresh", 0.5, 0.9)
        w_iv = trial.suggest_float("w_iv", 0.8, 2.8)
        w_snt = trial.suggest_float("w_snt", 0.5, 2.0)
        w_hv = trial.suggest_float("w_hv", -0.5, 0.5)
        hv_t = trial.suggest_categorical("hv_t", [10, 20, 30])
        decay_n = trial.suggest_int("decay_n", 15, 60)
        universe = trial.suggest_categorical("universe", ["TOP3000"])
        decay = trial.suggest_categorical("decay", [4, 6, 8])  # MID-RANGE ONLY
        truncation = trial.suggest_categorical("truncation", [0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY"])
        wrap_group_zscore = trial.suggest_categorical("wrap_group_zscore", [False, True])

        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(gate_kind, gate_thresh, w_iv, w_snt, w_hv,
                                hv_t, decay_n, wrap_group_zscore)
        log.info(f"t{trial.number}: gate={gate_kind}>{gate_thresh:.2f} w_iv={w_iv:.2f} "
                 f"w_snt={w_snt:.2f} w_hv={w_hv:+.2f} N={decay_n} | "
                 f"u={universe} dec={decay} tr={truncation} neut={neutralization[:5]} "
                 f"wrap={wrap_group_zscore}")
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
        if not res.ok: return -10.0
        if res.turnover > 0.5: return res.sharpe - 5.0
        check_bonus = (res.checks_passed - 4) * 0.5
        return res.sharpe + 0.1 * res.fitness + check_bonus

    def stop_when_found(study, trial):
        if found["alpha_id"]: study.stop()

    try:
        study.optimize(objective, n_trials=args.trials,
                        callbacks=[stop_when_found], show_progress_bar=False)
    except KeyboardInterrupt:
        return 130

    print("\n" + "=" * 100)
    if found["alpha_id"]:
        print(f"SURVIVOR: {found['alpha_id']}")
        return 0
    print("NO SURVIVOR. Best trial:")
    bt = study.best_trial
    print(f"  trial {bt.number}: value={bt.value:.3f} params={bt.params}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
