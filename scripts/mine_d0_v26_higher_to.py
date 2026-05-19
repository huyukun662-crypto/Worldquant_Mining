"""D0 v26 — push SH by allowing higher turnover.

v25 found SH=1.74 chk=6 with TO=0.056 (rKb89d3o). User insight: TO is
way below HIGH_TURNOVER limit (0.70), so we have budget to trade more
frequently. Higher TO usually means capturing more short-horizon alpha,
which can lift SH.

v26 keeps the v25 winning structure (iv_skew + snt + iv_term + rev_20
4-leg with scale wrap) but searches HIGHER TO regions:
  - decay_n 5-30 (v25 used 35-70)
  - platform decay 4-8 (v25 used 8-14)
  - gate_thresh 0.10-0.50 (v25 used 0.40-0.65, lower = wider trading window)
  - new gate_kind = "none" option (no news gate, max TO)

Hard constraint: turnover must stay < 0.50 to keep us comfortably under
WQ's 0.70 HIGH_TURNOVER limit. Penalize if TO > 0.50.

Risk: removing/loosening trade_when may break LOW_SUB_UNIVERSE_SHARPE
which the news gate solves. v25 chk=6 cluster was earned via news gate
concentration. v26 finds out how much TO can be raised before SUB
falls under threshold.
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
log = logging.getLogger("mine-v26")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V26_RESULTS.json"
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

LEG1 = "rank(implied_volatility_call_60 - implied_volatility_put_60)"  # iv_skew
LEG2 = "rank(snt_value)"

LEG3_OPTIONS = {
    "iv_term":      "rank(implied_volatility_mean_60 - implied_volatility_mean_30)",
    "iv_term_3060": "rank(implied_volatility_mean_30 - implied_volatility_mean_60)",
    "iv_vs_hv":     "rank(implied_volatility_mean_60 - historical_volatility_60)",
    "iv_mean_skew": "rank(implied_volatility_mean_skew_60)",
    "iv_skew_z":    "rank(ts_zscore(implied_volatility_call_60 - implied_volatility_put_60, 20))",
    "iv_mean_d5":   "rank(ts_delta(implied_volatility_mean_60, 5))",
}

LEG4_OPTIONS = {
    "rev_5":        "rank(-1 * ts_zscore(returns, 5))",
    "rev_10":       "rank(-1 * ts_zscore(returns, 10))",
    "rev_20":       "rank(-1 * ts_zscore(returns, 20))",
    "mom_5":        "rank(ts_zscore(returns, 5))",
    "mom_20":       "rank(ts_zscore(returns, 20))",
    "vwap_dev":     "rank((close - vwap) / (vwap + 0.01))",
    "vol_surp":     "rank(volume / (adv20 + 1.0))",
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
                     gate_kind: str, gate_thresh: float,
                     outer_wrap: str) -> str:
    body = (f"{w1:.2f} * {LEG1} + {w2:.2f} * {LEG2} "
            f"+ {w3:.2f} * {LEG3_OPTIONS[sig3]} + {w4:.2f} * {LEG4_OPTIONS[sig4]}")
    inner = f"ts_decay_linear({body}, {decay_n})"
    if gate_kind == "news_or":
        gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f})"
        inner = f"trade_when({gate}, {inner}, -1)"
    elif gate_kind == "news_and":
        gate = f"((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f}))"
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
    ap.add_argument("--seed", type=int, default=26262)
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

    # Seed: v25 winner with progressively shorter decays / wider gates
    base_seeds = [
        # v25 winner (TO=0.056)
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 47, "news_or", 0.47, "scale", 10, 0.08, "INDUSTRY"),
        # Shorter decay_n → higher TO
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 25, "news_or", 0.47, "scale", 10, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 15, "news_or", 0.47, "scale", 8, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 10, "news_or", 0.47, "scale", 6, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 5,  "news_or", 0.47, "scale", 4, 0.08, "INDUSTRY"),
        # Wider gate (more trading days)
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 25, "news_or", 0.30, "scale", 8, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 20, "news_or", 0.20, "scale", 6, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 15, "news_or", 0.10, "scale", 6, 0.08, "INDUSTRY"),
        # No gate (max TO; SUB may break, but worth trying)
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 25, "none", 0.50, "scale", 8, 0.08, "INDUSTRY"),
        ("iv_term", "rev_20", 1.57, 0.65, 0.89, 0.58, 15, "none", 0.50, "scale", 6, 0.08, "INDUSTRY"),
        # Shorter rev (rev_5 / rev_10) — faster signal
        ("iv_term", "rev_5",  1.57, 0.65, 0.89, 0.58, 25, "news_or", 0.47, "scale", 8, 0.08, "INDUSTRY"),
        ("iv_term", "rev_10", 1.57, 0.65, 0.89, 0.58, 25, "news_or", 0.47, "scale", 8, 0.08, "INDUSTRY"),
        ("iv_term", "rev_5",  1.57, 0.65, 0.89, 0.58, 15, "none", 0.50, "scale", 6, 0.08, "INDUSTRY"),
        # iv_mean_d5 (fast option signal)
        ("iv_mean_d5", "rev_5", 1.57, 0.65, 0.89, 0.58, 15, "news_or", 0.30, "scale", 6, 0.08, "INDUSTRY"),
        ("iv_skew_z",  "rev_5", 1.57, 0.65, 0.89, 0.58, 15, "news_or", 0.30, "scale", 6, 0.08, "INDUSTRY"),
    ]
    for sv in base_seeds:
        study.enqueue_trial({
            "sig3": sv[0], "sig4": sv[1],
            "w1": sv[2], "w2": sv[3], "w3": sv[4], "w4": sv[5],
            "decay_n": sv[6],
            "gate_kind": sv[7], "gate_thresh": sv[8],
            "outer_wrap": sv[9],
            "universe": "TOP3000",
            "decay": sv[10], "truncation": sv[11], "neutralization": sv[12],
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
        sig3 = trial.suggest_categorical("sig3", list(LEG3_OPTIONS))
        sig4 = trial.suggest_categorical("sig4", list(LEG4_OPTIONS))
        w1 = trial.suggest_float("w1", 1.20, 2.00)
        w2 = trial.suggest_float("w2", 0.40, 1.00)
        w3 = trial.suggest_float("w3", 0.60, 1.30)
        w4 = trial.suggest_float("w4", 0.30, 0.90)
        decay_n = trial.suggest_int("decay_n", 5, 30)            # SHORTER decay
        gate_kind = trial.suggest_categorical("gate_kind", ["news_or", "news_and", "none"])
        gate_thresh = trial.suggest_float("gate_thresh", 0.10, 0.50)  # WIDER gate
        outer_wrap = trial.suggest_categorical(
            "outer_wrap", ["scale", "winsorize_4", "scale_winsorize"])
        universe = trial.suggest_categorical("universe", ["TOP3000"])
        decay = trial.suggest_categorical("decay", [4, 5, 6, 8, 10])    # SMALLER decay (includes v25 baseline 10)
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY"])

        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(sig3, sig4, w1, w2, w3, w4,
                                 decay_n, gate_kind, gate_thresh, outer_wrap)
        log.info(f"t{trial.number}: {sig3}+{sig4} w={w1:.2f}/{w2:.2f}/{w3:.2f}/{w4:.2f} "
                 f"N={decay_n} gate={gate_kind}>{gate_thresh:.2f} wrap={outer_wrap} | "
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
        # Penalize TO > 0.50 (still below WQ 0.70 limit but risky)
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
