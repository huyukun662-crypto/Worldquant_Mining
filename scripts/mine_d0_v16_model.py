"""D0 v16 — TPE-search MODEL category fields (cov=1.00 → SUB auto-passes).

The model category has 3,281 pre-computed factor scores all at cov=1.0
across TOP3000. These are basically already-mined signals. Since they
have 100% coverage, LOW_SUB_UNIVERSE_SHARPE should pass automatically.

The hypothesis: with cov=1.0 the signal trades all stocks (not just
news-event stocks like trade_when restricts), so sub-universe behavior
matches main-universe behavior naturally.

v16 picks from a curated list of ~25 high-coverage meta-scores
(model16) and structural ML fields (model77), applies a simple
transformation (rank, ts_zscore, ts_delta), wraps in ts_decay_linear,
and searches universe/decay/neutralization.

No trade_when needed — model fields don't have the news-gate
TO-spike problem because they're slow-changing fundamental scores.
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
log = logging.getLogger("mine-v16")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V16_RESULTS.json"
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

# Curated model fields with cov=1.00. Mix of model16 meta-scores
# (factor blends) and model77 ML structural fields.
MODEL_FIELDS = [
    # ── model16 meta-scores (24 total, all composite)
    "composite_factor_score_derivative",
    "multi_factor_acceleration_score_derivative",
    "multi_factor_static_score_derivative",
    "analyst_revision_rank_derivative",
    "cashflow_efficiency_rank_derivative",
    "earnings_certainty_rank_derivative",
    "growth_potential_rank_derivative",
    "relative_valuation_rank_derivative",
    # ── model77 high-conviction ML scores
    "equity_value_score",
    "enterprise_value_weighted_value_score",
    "earnings_momentum_composite_score",
    "earnings_momentum_composite_score_2",
    "earnings_momentum_analyst_score",
    "earnings_expectation_module_score",
    "consensus_analyst_rating",
    "abnormal_return_earnings_release",
    "change_in_eps_surprise",
    "earnings_shortfall_metric",
    "earnings_torpedo_indicator",
    "fcf_yield_times_forward_roe",
    "credit_risk_premium_indicator",
    "coefficient_variation_fy2_eps",
    "book_leverage_ratio_3",
    "capex_to_total_assets",
    "dividends_to_gross_profit",
]

TRANSFORMS = ["rank", "ts_zscore_20", "ts_zscore_60", "ts_delta_5"]


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


def transform_field(name: str, transform: str) -> str:
    if transform == "rank":
        return f"rank({name})"
    if transform == "ts_zscore_20":
        return f"rank(ts_zscore({name}, 20))"
    if transform == "ts_zscore_60":
        return f"rank(ts_zscore({name}, 60))"
    if transform == "ts_delta_5":
        return f"rank(ts_delta({name}, 5))"
    raise ValueError(transform)


def build_expression(field1: str, t1: str,
                     field2: str | None, t2: str | None,
                     w1: float, w2: float, decay_n: int) -> str:
    leg1 = transform_field(field1, t1)
    if field2 and field2 != field1:
        leg2 = transform_field(field2, t2)
        body = f"{w1:.2f} * {leg1} + {w2:.2f} * {leg2}"
    else:
        body = f"{w1:.2f} * {leg1}"
    return f"ts_decay_linear({body}, {decay_n})"


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
    ap.add_argument("--seed", type=int, default=16161)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=12)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed with model16 composite-score-derivative single-leg trials
    for fld in MODEL_FIELDS[:8]:
        study.enqueue_trial({
            "field1": fld, "t1": "rank",
            "field2_idx": -1, "t2": "rank",
            "w1": 1.0, "w2": 0.0,
            "decay_n": 10,
            "universe": "TOP3000", "decay": 4,
            "truncation": 0.08, "neutralization": "INDUSTRY",
        })

    found = {"alpha_id": None}

    def objective(trial: optuna.trial.Trial) -> float:
        field1 = trial.suggest_categorical("field1", MODEL_FIELDS)
        t1 = trial.suggest_categorical("t1", TRANSFORMS)
        # field2_idx -1 means no second leg
        field2_idx = trial.suggest_int("field2_idx", -1, len(MODEL_FIELDS) - 1)
        t2 = trial.suggest_categorical("t2", TRANSFORMS)
        w1 = trial.suggest_float("w1", 0.5, 2.0)
        w2 = trial.suggest_float("w2", 0.3, 1.5)
        decay_n = trial.suggest_int("decay_n", 5, 30)
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])
        decay = trial.suggest_categorical("decay", [4, 6, 8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY", "SECTOR"])

        field2 = MODEL_FIELDS[field2_idx] if field2_idx >= 0 else None
        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(field1, t1, field2, t2, w1, w2, decay_n)
        log.info(f"t{trial.number}: f1={field1[:25]}({t1}) "
                 f"f2={(field2 or '-')[:25]}({t2}) w={w1:.2f}/{w2:.2f} N={decay_n} | "
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
