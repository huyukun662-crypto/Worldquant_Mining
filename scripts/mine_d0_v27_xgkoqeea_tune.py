"""D0 v27 — ultra-focused TPE around v26 SH=1.94 winner XgkOqEea.

XgkOqEea actual config (SH=1.94 FIT=1.81 TO=0.096 chk=6):
  outer_wrap=winsorize_4 (NOT scale)
  gate=news_or > 0.186 (very wide)
  w1=1.90, w2=0.96, w3=1.15, w4=0.39
  decay_n=26, decay=10, truncation=0.05, neutralization=INDUSTRY
  sig3=iv_mean_d5 (rank(ts_delta(iv_mean_60, 5)))
  sig4=rev_10 (rank(-ts_zscore(returns, 10)))

v27 narrows everything tight to this neighborhood + explores:
  - iv_mean_d5 delta window (3, 4, 5, 6, 8) — current uses 5
  - winsorize std (3, 4, 5, 6) — current is 4
  - higher w1 (1.85-2.20) — current pushed to 1.90
  - tighter truncation (0.03, 0.05, 0.08)
  - mom_5/rev_5 alternates for sig4 — faster reversal

Goal: push SH 1.94 → 2.00+ to break LOW_SHARPE.
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
log = logging.getLogger("mine-v27")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V27_RESULTS.json"
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

# Fixed legs
LEG1 = "rank(implied_volatility_call_60 - implied_volatility_put_60)"
LEG2 = "rank(snt_value)"


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


def make_leg3(iv_d_window: int, iv_field: str) -> str:
    # iv_field selects which IV variable to delta
    fld = {
        "mean_60":  "implied_volatility_mean_60",
        "mean_30":  "implied_volatility_mean_30",
        "call_60":  "implied_volatility_call_60",
        "put_60":   "implied_volatility_put_60",
        "skew_60":  "implied_volatility_mean_skew_60",
    }[iv_field]
    return f"rank(ts_delta({fld}, {iv_d_window}))"


def make_leg4(name: str) -> str:
    return {
        "rev_5":   "rank(-1 * ts_zscore(returns, 5))",
        "rev_10":  "rank(-1 * ts_zscore(returns, 10))",
        "rev_15":  "rank(-1 * ts_zscore(returns, 15))",
        "rev_20":  "rank(-1 * ts_zscore(returns, 20))",
        "mom_5":   "rank(ts_zscore(returns, 5))",
    }[name]


def build_expression(iv_d_window: int, iv_field: str, sig4: str,
                     w1: float, w2: float, w3: float, w4: float,
                     decay_n: int,
                     gate_thresh: float,
                     wins_std: int) -> str:
    leg3 = make_leg3(iv_d_window, iv_field)
    leg4 = make_leg4(sig4)
    body = f"{w1:.3f} * {LEG1} + {w2:.3f} * {LEG2} + {w3:.3f} * {leg3} + {w4:.3f} * {leg4}"
    inner = f"ts_decay_linear({body}, {decay_n})"
    gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.3f})"
    inner = f"trade_when({gate}, {inner}, -1)"
    inner = f"winsorize({inner}, std={wins_std})"
    return inner


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
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--seed", type=int, default=27272)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=18)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seeds: exact XgkOqEea + tight variants
    seeds = [
        # XgkOqEea exact
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        # Higher w1
        (5, "mean_60", "rev_10", 2.00, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        (5, "mean_60", "rev_10", 2.10, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        # Different iv_d window
        (3, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        (4, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        (6, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        (8, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        # Different iv field for delta
        (5, "mean_30", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        (5, "call_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        (5, "skew_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        # Different winsorize std
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 3, 0.05, 10),
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 5, 0.05, 10),
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 6, 0.05, 10),
        # Different truncation
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.03, 10),
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.08, 10),
        # Different decay_n
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 22, 0.186, 4, 0.05, 10),
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 30, 0.186, 4, 0.05, 10),
        # Wider/tighter gate
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.10, 4, 0.05, 10),
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.15, 0.39, 26, 0.25, 4, 0.05, 10),
        # Higher w3 (more iv_mean_d5)
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.40, 0.39, 26, 0.186, 4, 0.05, 10),
        (5, "mean_60", "rev_10", 1.90, 0.96, 1.60, 0.39, 26, 0.186, 4, 0.05, 10),
        # Different sig4
        (5, "mean_60", "rev_5",  1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        (5, "mean_60", "rev_15", 1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
        (5, "mean_60", "mom_5",  1.90, 0.96, 1.15, 0.39, 26, 0.186, 4, 0.05, 10),
    ]
    for sv in seeds:
        study.enqueue_trial({
            "iv_d_window": sv[0], "iv_field": sv[1], "sig4": sv[2],
            "w1": sv[3], "w2": sv[4], "w3": sv[5], "w4": sv[6],
            "decay_n": sv[7], "gate_thresh": sv[8], "wins_std": sv[9],
            "truncation": sv[10], "decay": sv[11],
        })

    found = {"alpha_id": None}
    seen_alphas: set[str] = set()
    seen_exprs: dict[str, str] = {}
    if RESULTS_FILE.exists():
        try:
            for x in json.loads(RESULTS_FILE.read_text()):
                if x.get("ok") and x.get("alpha_id"):
                    seen_alphas.add(x["alpha_id"])
                s = x.get("settings", {})
                key = (x.get("expression", ""), s.get("universe"),
                       s.get("delay"), s.get("decay"),
                       s.get("truncation"), s.get("neutralization"))
                if x.get("expression"):
                    seen_exprs[str(key)] = x.get("alpha_id", "?")
        except Exception:
            pass
    log.info(f"resume: {len(seen_alphas)} alpha_ids, {len(seen_exprs)} expr-settings skip-list")

    def objective(trial: optuna.trial.Trial) -> float:
        iv_d_window = trial.suggest_int("iv_d_window", 3, 10)
        iv_field = trial.suggest_categorical(
            "iv_field", ["mean_60", "mean_30", "call_60", "put_60", "skew_60"])
        sig4 = trial.suggest_categorical("sig4", ["rev_5", "rev_10", "rev_15", "rev_20", "mom_5"])
        w1 = trial.suggest_float("w1", 1.70, 2.30)
        w2 = trial.suggest_float("w2", 0.70, 1.20)
        w3 = trial.suggest_float("w3", 0.90, 1.70)
        w4 = trial.suggest_float("w4", 0.20, 0.60)
        decay_n = trial.suggest_int("decay_n", 18, 35)
        gate_thresh = trial.suggest_float("gate_thresh", 0.08, 0.35)
        wins_std = trial.suggest_int("wins_std", 3, 6)
        truncation = trial.suggest_categorical("truncation", [0.03, 0.05, 0.08])
        decay = trial.suggest_categorical("decay", [8, 10, 12])

        settings = dict(FIXED_SETTINGS)
        settings.update(universe="TOP3000", decay=decay,
                        truncation=truncation, neutralization="INDUSTRY")

        expr = build_expression(iv_d_window, iv_field, sig4,
                                 w1, w2, w3, w4, decay_n,
                                 gate_thresh, wins_std)
        log.info(f"t{trial.number}: iv_d({iv_field})/{iv_d_window}+{sig4} "
                 f"w={w1:.2f}/{w2:.2f}/{w3:.2f}/{w4:.2f} N={decay_n} "
                 f"gate>{gate_thresh:.2f} wins={wins_std} tr={truncation} dec={decay}")
        expr_key = str((expr, settings.get("universe"), settings.get("delay"),
                         settings.get("decay"), settings.get("truncation"),
                         settings.get("neutralization")))
        if expr_key in seen_exprs:
            log.info(f"  (skip — already simulated as {seen_exprs[expr_key]})")
            return -5.0

        res = wq_submit(session, expr, settings)
        if res.ok and res.alpha_id:
            seen_exprs[expr_key] = res.alpha_id

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
            if res.alpha_id and res.alpha_id not in seen_alphas:
                seen_alphas.add(res.alpha_id)
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
        if res.turnover > 0.50:
            return res.sharpe - 2.0
        check_bonus = (res.checks_passed - 4) * 0.5
        return res.sharpe + 0.1 * res.fitness + check_bonus

    try:
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)
    except KeyboardInterrupt:
        return 130

    print()
    print("=" * 100)
    print(f"DONE — last accepted: {found.get('alpha_id')!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
