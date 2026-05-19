"""D0 v24 — push the v11 chk=6 ceiling via 3rd/4th leg + extrema operators.

The v11 chk=6 winning recipe caps at SH 1.66 with only LOW_SHARPE failing:
  trade_when(news_gate, ts_decay_linear(w1*rank(iv_call60 - iv_put60)
             + w2*rank(snt_value), N), -1)

v23 attempts to break the wall via pure-PV Alpha101 templates failed
(SH cap ~1.0 pure PV). User has authorized mixing back in. v24 keeps the
v11 chk=6 backbone (iv_skew + snt + trade_when) and adds a TPE-selectable
3rd leg + optional 4th leg from an expanded library that includes:
  - PV signals (momentum/reversion/microstructure/volume)
  - Option signals (iv_term, iv_vs_hv, mean_skew, pcr_oi_60)
  - Pool C extrema/skew from v23 (the operators v11-v22 never used)

Goal: push SH from 1.66 → 1.8-2.0+ while preserving chk=6/8 (especially
LOW_SUB_UNIVERSE_SHARPE which the trade_when gate already passes).
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
log = logging.getLogger("mine-v24")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V24_RESULTS.json"
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

# Fixed legs that anchor v24 in the v11 chk=6 region.
LEG1 = "rank(implied_volatility_call_60 - implied_volatility_put_60)"
LEG2 = "rank(snt_value)"

# 3rd-leg / 4th-leg candidate library. Mix of:
#  - PV signals (momentum, reversion, microstructure, volume)
#  - Option signals (iv_term, iv_vs_hv, mean_skew, pcr_oi_60)
#  - Pool C extrema/skew (untried in v11-v22; some confirmed working in v23)
EXTRA_SIGNALS: dict[str, str] = {
    # PV
    "mom_5":         "rank(ts_zscore(returns, 5))",
    "mom_20":        "rank(ts_zscore(returns, 20))",
    "mom_60":        "rank(ts_zscore(returns, 60))",
    "rev_5":         "rank(-1 * ts_zscore(returns, 5))",
    "rev_20":        "rank(-1 * ts_zscore(returns, 20))",
    "vs_ma60":       "rank(close / ts_mean(close, 60) - 1.0)",
    "vwap_dev":      "rank((close - vwap) / (vwap + 0.01))",
    "vol_surp":      "rank(volume / (adv20 + 1.0))",
    "pv_corr":       "rank(ts_corr(close, volume, 30))",
    "pv_corr_n":     "rank(-1 * ts_corr(close, volume, 30))",
    "lowvol":        "rank(-1 * ts_std_dev(returns, 60))",
    "intra":         "rank((close - open) / (open + 0.01))",
    # Option
    "iv_term":       "rank(implied_volatility_mean_60 - implied_volatility_mean_30)",
    "iv_vs_hv":      "rank(implied_volatility_mean_60 - historical_volatility_60)",
    "iv_mean_skew":  "rank(implied_volatility_mean_skew_60)",
    "pcr_n":         "rank(-1 * pcr_oi_60)",
    "iv_skew_z":     "rank(ts_zscore(implied_volatility_call_60 - implied_volatility_put_60, 20))",
    # Sentiment / news
    "snt_buzz":      "rank(snt_buzz)",
    "snt_z20":       "rank(ts_zscore(snt_value, 20))",
    "news30":        "rank(news_pct_30min)",
    # Pool C extrema (untried in v11-v22; ts_min/ts_max blocked, but arg_max OK)
    "argmax_dist":   "rank((20 - ts_arg_max(close, 20)) / 20)",
    "argmin_dist":   "rank((20 - ts_arg_min(close, 20)) / 20)",
    "skew_neg":      "rank(-1 * ts_skewness(returns, 60))",
    "kurt":          "rank(-1 * ts_kurtosis(returns, 60))",
    "vol_arg":       "rank(ts_arg_max(ts_std_dev(returns, 20), 60))",
    "corr_skew":     "rank(ts_corr(rank(returns), ts_skewness(returns, 20), 30))",
    "decay_sp":      "ts_decay_linear(signed_power(ts_zscore(returns, 20), 0.5), 10)",
    "a040":          "(-1 * rank(ts_std_dev(high, 10))) * ts_corr(high, volume, 20)",  # v23 best singleton
    "a006":          "-1 * ts_corr(open, volume, 10)",
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


def build_expression(sig3: str | None, sig4: str | None,
                     w1: float, w2: float, w3: float, w4: float,
                     decay_n: int,
                     gate_kind: str, gate_thresh: float,
                     outer_wrap: str) -> str:
    parts = [f"{w1:.2f} * {LEG1}", f"{w2:.2f} * {LEG2}"]
    if sig3 and sig3 != "none":
        parts.append(f"{w3:.2f} * {EXTRA_SIGNALS[sig3]}")
    if sig4 and sig4 != "none" and sig4 != sig3:
        parts.append(f"{w4:.2f} * {EXTRA_SIGNALS[sig4]}")
    body = " + ".join(parts)
    inner = f"ts_decay_linear({body}, {decay_n})"
    if gate_kind == "news_or":
        gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f})"
        inner = f"trade_when({gate}, {inner}, -1)"
    elif gate_kind == "news_and":
        gate = f"((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f}))"
        inner = f"trade_when({gate}, {inner}, -1)"
    if outer_wrap == "winsorize_4":
        inner = f"winsorize({inner}, std=4)"
    elif outer_wrap == "scale":
        inner = f"scale({inner})"
    elif outer_wrap == "group_neut_subindustry":
        inner = f"group_neutralize({inner}, subindustry)"
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
    ap.add_argument("--trials", type=int, default=150)
    ap.add_argument("--seed", type=int, default=24242)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=25)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    sig_names = list(EXTRA_SIGNALS) + ["none"]

    # Seed 1: v11 chk=6 winning recipe (no 3rd/4th leg)
    study.enqueue_trial({
        "sig3": "none", "sig4": "none",
        "w1": 1.11, "w2": 0.87, "w3": 0.30, "w4": 0.20,
        "decay_n": 40,
        "gate_kind": "news_and", "gate_thresh": 0.54,
        "outer_wrap": "none",
        "universe": "TOP3000", "decay": 4,
        "truncation": 0.05, "neutralization": "INDUSTRY",
    })
    study.enqueue_trial({
        "sig3": "none", "sig4": "none",
        "w1": 1.30, "w2": 0.80, "w3": 0.30, "w4": 0.20,
        "decay_n": 35,
        "gate_kind": "news_or", "gate_thresh": 0.60,
        "outer_wrap": "none",
        "universe": "TOP3000", "decay": 8,
        "truncation": 0.08, "neutralization": "INDUSTRY",
    })
    # Seed 2: try each extra signal as 3rd leg with v11 chk=6 baseline
    for sig in EXTRA_SIGNALS:
        study.enqueue_trial({
            "sig3": sig, "sig4": "none",
            "w1": 1.30, "w2": 0.80, "w3": 0.40, "w4": 0.20,
            "decay_n": 30,
            "gate_kind": "news_or", "gate_thresh": 0.60,
            "outer_wrap": "none",
            "universe": "TOP3000", "decay": 6,
            "truncation": 0.08, "neutralization": "INDUSTRY",
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
        sig3 = trial.suggest_categorical("sig3", sig_names)
        sig4 = trial.suggest_categorical("sig4", sig_names)
        w1 = trial.suggest_float("w1", 0.8, 1.8)
        w2 = trial.suggest_float("w2", 0.4, 1.2)
        w3 = trial.suggest_float("w3", 0.2, 1.0)
        w4 = trial.suggest_float("w4", 0.1, 0.7)
        decay_n = trial.suggest_int("decay_n", 5, 50)
        gate_kind = trial.suggest_categorical(
            "gate_kind", ["news_or", "news_and"])
        gate_thresh = trial.suggest_float("gate_thresh", 0.45, 0.80)
        outer_wrap = trial.suggest_categorical(
            "outer_wrap", ["none", "winsorize_4", "scale", "group_neut_subindustry"])
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])
        decay = trial.suggest_categorical("decay", [4, 6, 8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "FAST"])

        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(sig3, sig4, w1, w2, w3, w4,
                                 decay_n, gate_kind, gate_thresh, outer_wrap)
        legs_label = f"{sig3 or 'none'}+{sig4 or 'none'}"
        log.info(f"t{trial.number}: legs3/4={legs_label} w={w1:.2f}/{w2:.2f}/{w3:.2f}/{w4:.2f} "
                 f"N={decay_n} gate={gate_kind}>{gate_thresh:.2f} wrap={outer_wrap} | "
                 f"u={universe} dec={decay} tr={truncation} neut={neutralization[:5]}")
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
