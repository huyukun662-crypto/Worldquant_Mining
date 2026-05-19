"""D0 v25 — Focused TPE around v24 SH=1.72 chk=6 sweet spot.

v24 discovered a winning recipe at SH=1.72 chk=6 with FIT=1.51:

    scale(trade_when((ts_rank(abs(news_pct_30min), 60) > 0.47),
      ts_decay_linear(
        1.57 * rank(iv_call60 - iv_put60)        # iv_skew
        + 0.65 * rank(snt_value)                 # snt
        + 0.89 * rank(iv_mean_60 - iv_mean_30)   # iv_term
        + 0.58 * rank(-ts_zscore(returns, 20)),  # rev_20
        47), -1))

Settings: TOP3000 / delay=0 / decay=10 / truncation=0.08 / INDUSTRY

v25 keeps the structure fixed (iv_skew + snt + iv_term + rev_20 ALWAYS
present) and tightly searches around the proven weights/windows/wraps
to push past 1.72. Also tries swapping rev_20 for adjacent variants
(rev_5, rev_60, mom_20, snt_z20) and iv_term for adjacent option-IV
variants (iv_skew_z, iv_vs_hv, iv_mean_skew).

The aggressive TPE search of v24 wasted budget re-exploring weak
regions; v25 narrows the search to the productive neighborhood.
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
log = logging.getLogger("mine-v25")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V25_RESULTS.json"
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

# Anchored legs (always present).
LEG1 = "rank(implied_volatility_call_60 - implied_volatility_put_60)"  # iv_skew
LEG2 = "rank(snt_value)"                                                # snt

# Leg3 candidates — option-family variants of iv_term (proven 3rd leg)
LEG3_OPTIONS = {
    "iv_term":      "rank(implied_volatility_mean_60 - implied_volatility_mean_30)",
    "iv_term_3060": "rank(implied_volatility_mean_30 - implied_volatility_mean_60)",
    "iv_vs_hv":     "rank(implied_volatility_mean_60 - historical_volatility_60)",
    "iv_mean_skew": "rank(implied_volatility_mean_skew_60)",
    "iv_skew_z":    "rank(ts_zscore(implied_volatility_call_60 - implied_volatility_put_60, 20))",
    "iv_level":     "rank(implied_volatility_mean_60)",
    "iv_mean_d5":   "rank(ts_delta(implied_volatility_mean_60, 5))",
}

# Leg4 candidates — reversal/momentum/sentiment variants of rev_20 (proven 4th leg)
LEG4_OPTIONS = {
    "rev_20":       "rank(-1 * ts_zscore(returns, 20))",
    "rev_5":        "rank(-1 * ts_zscore(returns, 5))",
    "rev_60":       "rank(-1 * ts_zscore(returns, 60))",
    "mom_20":       "rank(ts_zscore(returns, 20))",
    "snt_z20":      "rank(ts_zscore(snt_value, 20))",
    "pv_corr":      "rank(ts_corr(close, volume, 30))",
    "lowvol":       "rank(-1 * ts_std_dev(returns, 60))",
    "vs_ma60":      "rank(close / ts_mean(close, 60) - 1.0)",
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


def build_expression(sig3: str, sig4: str,
                     w1: float, w2: float, w3: float, w4: float,
                     decay_n: int,
                     gate_thresh: float,
                     outer_wrap: str) -> str:
    body = (f"{w1:.2f} * {LEG1} + {w2:.2f} * {LEG2} "
            f"+ {w3:.2f} * {LEG3_OPTIONS[sig3]} + {w4:.2f} * {LEG4_OPTIONS[sig4]}")
    inner = f"ts_decay_linear({body}, {decay_n})"
    gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f})"
    inner = f"trade_when({gate}, {inner}, -1)"
    if outer_wrap == "scale":
        inner = f"scale({inner})"
    elif outer_wrap == "winsorize_4":
        inner = f"winsorize({inner}, std=4)"
    elif outer_wrap == "scale_winsorize":
        inner = f"scale(winsorize({inner}, std=4))"
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
    ap.add_argument("--seed", type=int, default=25252)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=15)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed exact v24 winner config first
    study.enqueue_trial({
        "sig3": "iv_term", "sig4": "rev_20",
        "w1": 1.57, "w2": 0.65, "w3": 0.89, "w4": 0.58,
        "decay_n": 47,
        "gate_thresh": 0.47,
        "outer_wrap": "scale",
        "universe": "TOP3000", "decay": 10,
        "truncation": 0.08, "neutralization": "INDUSTRY",
    })
    # Variations on the winner
    seed_variants = [
        # Push w1 higher
        ("iv_term", "rev_20", 1.80, 0.60, 0.85, 0.55, 50, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.95, 0.55, 0.80, 0.50, 50, 0.45, "scale", 10, 0.08, "INDUSTRY"),
        # Push decay_n higher
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 60, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 75, 0.47, "scale", 12, 0.08, "INDUSTRY"),
        # Try scale_winsorize wrap
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale_winsorize", 10, 0.08, "INDUSTRY"),
        # Tighter gate
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.60, "scale", 10, 0.08, "INDUSTRY"),
        # SUBINDUSTRY neut
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "SUBINDUSTRY"),
        # truncation tweaks
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.05, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.10, "INDUSTRY"),
        # decay tweaks
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 8, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 12, 0.08, "INDUSTRY"),
        # Swap leg3 candidates with same other settings
        ("iv_skew_z", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_vs_hv", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_mean_skew", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_mean_d5", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        # Swap leg4 candidates
        ("iv_term", "rev_5", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_term", "rev_60", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_term", "snt_z20", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_term", "pv_corr", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_term", "lowvol", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_term", "vs_ma60", 1.57, 0.65, 0.89, 0.58, 47, 0.47, "scale", 10, 0.08, "INDUSTRY"),
    ]
    for sv in seed_variants:
        study.enqueue_trial({
            "sig3": sv[0], "sig4": sv[1],
            "w1": sv[2], "w2": sv[3], "w3": sv[4], "w4": sv[5],
            "decay_n": sv[6], "gate_thresh": sv[7],
            "outer_wrap": sv[8],
            "universe": "TOP3000",
            "decay": sv[9], "truncation": sv[10], "neutralization": sv[11],
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
        # TIGHT search around v24 sweet spot
        sig3 = trial.suggest_categorical("sig3", list(LEG3_OPTIONS))
        sig4 = trial.suggest_categorical("sig4", list(LEG4_OPTIONS))
        w1 = trial.suggest_float("w1", 1.20, 2.00)
        w2 = trial.suggest_float("w2", 0.40, 1.00)
        w3 = trial.suggest_float("w3", 0.60, 1.30)
        w4 = trial.suggest_float("w4", 0.30, 0.90)
        decay_n = trial.suggest_int("decay_n", 35, 70)
        gate_thresh = trial.suggest_float("gate_thresh", 0.40, 0.65)
        outer_wrap = trial.suggest_categorical(
            "outer_wrap", ["scale", "winsorize_4", "scale_winsorize"])
        universe = trial.suggest_categorical("universe", ["TOP3000"])
        decay = trial.suggest_categorical("decay", [8, 10, 12, 14])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY"])

        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(sig3, sig4, w1, w2, w3, w4,
                                 decay_n, gate_thresh, outer_wrap)
        log.info(f"t{trial.number}: {sig3}+{sig4} w={w1:.2f}/{w2:.2f}/{w3:.2f}/{w4:.2f} "
                 f"N={decay_n} gate>{gate_thresh:.2f} wrap={outer_wrap} | "
                 f"dec={decay} tr={truncation} neut={neutralization[:5]}")
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
        if res.turnover > 0.7:
            return res.sharpe - 5.0
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
