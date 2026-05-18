"""D0 v20 — PV + OPTION + SENTIMENT + NEWS (user-extended scope).

User scope: D0 mining, 量价 (PV) + 期权 (OPTION) primary, sentiment 和
news 也行. Fundamentals stay out.

Compared to v19, adds:
  - 5 SENTIMENT/NEWS signals (snt_value, snt_buzz, news intensity ranks)
  - TPE-selectable trade_when news gate (none | news_or | news_and)

D0 thresholds: LOW_SHARPE>=2.0, LOW_FITNESS>=1.30, LOW_SUB>=0.43*SH.
The v11-v15 chk=6 cluster (SH 1.66) lives in this space — already known
to satisfy SUB+FIT+CW. v20 attempts to push SH from 1.66 → 2.0 by
exploring 2-3 leg blends combining PV/OPT/SENT signals under the news
gate.
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
log = logging.getLogger("mine-v20")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V20_RESULTS.json"
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

PV_SIGNALS: dict[str, str] = {
    "mom_5":     "rank(ts_zscore(returns, 5))",
    "mom_20":    "rank(ts_zscore(returns, 20))",
    "mom_60":    "rank(ts_zscore(returns, 60))",
    "rev_5":     "rank(-1 * ts_zscore(returns, 5))",
    "rev_20":    "rank(-1 * ts_zscore(returns, 20))",
    "vs_ma20":   "rank(close / ts_mean(close, 20) - 1.0)",
    "vs_ma60":   "rank(close / ts_mean(close, 60) - 1.0)",
    "intra":     "rank((close - open) / (open + 0.01))",
    "range":     "rank((high - low) / (close + 0.01))",
    "vwap_dev":  "rank((close - vwap) / (vwap + 0.01))",
    "vol_surp":  "rank(volume / (adv20 + 1.0))",
    "vol_z":     "rank(ts_zscore(volume, 60))",
    "pv_corr":   "rank(ts_corr(close, volume, 30))",
    "pv_corr_n": "rank(-1 * ts_corr(close, volume, 30))",
    "lowvol":    "rank(-1 * ts_std_dev(returns, 60))",
    "vol_20":    "rank(ts_std_dev(returns, 20))",
}

OPT_SIGNALS: dict[str, str] = {
    "iv_skew":      "rank(implied_volatility_call_60 - implied_volatility_put_60)",
    "iv_term":      "rank(implied_volatility_mean_60 - implied_volatility_mean_30)",
    "iv_term_n":    "rank(implied_volatility_mean_30 - implied_volatility_mean_60)",
    "iv_vs_hv":     "rank(implied_volatility_mean_60 - historical_volatility_60)",
    "hv_vs_iv":     "rank(historical_volatility_60 - implied_volatility_mean_60)",
    "iv_mean_skew": "rank(implied_volatility_mean_skew_60)",
    "pcr":          "rank(-1 * pcr_oi_60)",
    "pcr_pos":      "rank(pcr_oi_60)",
    "iv_level":     "rank(implied_volatility_mean_60)",
    "iv_level_n":   "rank(-1 * implied_volatility_mean_60)",
    "iv_skew_z":    "rank(ts_zscore(implied_volatility_call_60 - implied_volatility_put_60, 20))",
    "iv_mean_d5":   "rank(ts_delta(implied_volatility_mean_60, 5))",
}

SNT_SIGNALS: dict[str, str] = {
    "snt":         "rank(snt_value)",
    "snt_z":       "rank(ts_zscore(snt_value, 20))",
    "snt_buzz":    "rank(snt_buzz)",
    "news_30":     "rank(news_pct_30min)",
    "news_z":      "rank(ts_zscore(abs(news_pct_30min), 60))",
}

ALL_SIGNALS: dict[str, str] = {**PV_SIGNALS, **OPT_SIGNALS, **SNT_SIGNALS}


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


def build_expression(sigs: list[str], weights: list[float],
                     decay_n: int, neut_wrap: str,
                     gate_kind: str, gate_thresh: float) -> str:
    parts = [f"{w:.2f} * {ALL_SIGNALS[s]}" for s, w in zip(sigs, weights)]
    body = " + ".join(parts)
    inner = f"ts_decay_linear({body}, {decay_n})"
    # Optional trade_when news gate
    if gate_kind == "news_or":
        gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f})"
        inner = f"trade_when({gate}, {inner}, -1)"
    elif gate_kind == "news_and":
        gate = f"((news_pct_90min < 1.0) * (ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.2f}))"
        inner = f"trade_when({gate}, {inner}, -1)"
    if neut_wrap != "none":
        inner = f"group_neutralize({inner}, {neut_wrap})"
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
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--seed", type=int, default=20202)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=20)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    sig_names = list(ALL_SIGNALS)

    # Seed promising 1-leg and 2-leg combos from prior work
    seed_trials = [
        # The v11 chk=6 winning recipe: iv_skew + snt_value + news_or gate
        {"sig1_idx": sig_names.index("iv_skew"),
         "sig2_idx": sig_names.index("snt"), "sig3_idx": -1,
         "w1": 1.30, "w2": 0.80, "w3": 0.3, "decay_n": 35,
         "neut_wrap": "none", "gate_kind": "news_or", "gate_thresh": 0.60,
         "universe": "TOP3000", "decay": 8, "truncation": 0.08,
         "neutralization": "INDUSTRY"},
        # Same with tight decay (chk=6 78x3JqY1 config)
        {"sig1_idx": sig_names.index("iv_skew"),
         "sig2_idx": sig_names.index("snt"), "sig3_idx": -1,
         "w1": 1.11, "w2": 0.87, "w3": 0.3, "decay_n": 40,
         "neut_wrap": "none", "gate_kind": "news_and", "gate_thresh": 0.54,
         "universe": "TOP3000", "decay": 4, "truncation": 0.05,
         "neutralization": "INDUSTRY"},
        # Adding a 3rd leg from PV — momentum/reversion
        {"sig1_idx": sig_names.index("iv_skew"),
         "sig2_idx": sig_names.index("snt"),
         "sig3_idx": sig_names.index("mom_20"),
         "w1": 1.30, "w2": 0.80, "w3": 0.30, "decay_n": 30,
         "neut_wrap": "none", "gate_kind": "news_or", "gate_thresh": 0.60,
         "universe": "TOP3000", "decay": 8, "truncation": 0.08,
         "neutralization": "INDUSTRY"},
        {"sig1_idx": sig_names.index("iv_skew"),
         "sig2_idx": sig_names.index("snt"),
         "sig3_idx": sig_names.index("rev_5"),
         "w1": 1.30, "w2": 0.80, "w3": 0.30, "decay_n": 30,
         "neut_wrap": "none", "gate_kind": "news_or", "gate_thresh": 0.60,
         "universe": "TOP3000", "decay": 8, "truncation": 0.08,
         "neutralization": "INDUSTRY"},
        # IV-skew + vwap_dev (microstructure 3rd leg)
        {"sig1_idx": sig_names.index("iv_skew"),
         "sig2_idx": sig_names.index("snt"),
         "sig3_idx": sig_names.index("vwap_dev"),
         "w1": 1.20, "w2": 0.80, "w3": 0.40, "decay_n": 25,
         "neut_wrap": "none", "gate_kind": "news_or", "gate_thresh": 0.55,
         "universe": "TOP3000", "decay": 6, "truncation": 0.08,
         "neutralization": "INDUSTRY"},
        # Single-leg seeds for each signal
    ]
    for s in sig_names:
        seed_trials.append({
            "sig1_idx": sig_names.index(s), "sig2_idx": -1, "sig3_idx": -1,
            "w1": 1.0, "w2": 0.5, "w3": 0.3, "decay_n": 5,
            "neut_wrap": "none", "gate_kind": "none", "gate_thresh": 0.6,
            "universe": "TOP3000", "decay": 4, "truncation": 0.08,
            "neutralization": "INDUSTRY",
        })
    for st in seed_trials:
        study.enqueue_trial(st)

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
        sig1_idx = trial.suggest_int("sig1_idx", 0, len(sig_names) - 1)
        sig2_idx = trial.suggest_int("sig2_idx", -1, len(sig_names) - 1)
        sig3_idx = trial.suggest_int("sig3_idx", -1, len(sig_names) - 1)
        w1 = trial.suggest_float("w1", 0.5, 2.0)
        w2 = trial.suggest_float("w2", 0.3, 1.5)
        w3 = trial.suggest_float("w3", 0.2, 1.0)
        decay_n = trial.suggest_int("decay_n", 3, 50)
        neut_wrap = trial.suggest_categorical(
            "neut_wrap", ["none", "sector", "subindustry"])
        gate_kind = trial.suggest_categorical(
            "gate_kind", ["none", "news_or", "news_and"])
        gate_thresh = trial.suggest_float("gate_thresh", 0.45, 0.85)
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])
        decay = trial.suggest_categorical("decay", [4, 6, 8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY", "SECTOR"])

        chosen = [sig_names[sig1_idx]]
        weights = [w1]
        if sig2_idx >= 0 and sig_names[sig2_idx] != chosen[0]:
            chosen.append(sig_names[sig2_idx]); weights.append(w2)
        if sig3_idx >= 0 and sig_names[sig3_idx] not in chosen:
            chosen.append(sig_names[sig3_idx]); weights.append(w3)

        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(chosen, weights, decay_n,
                                 neut_wrap, gate_kind, gate_thresh)
        log.info(f"t{trial.number}: sigs={'+'.join(chosen)} w={'/'.join(f'{w:.2f}' for w in weights)} "
                 f"N={decay_n} gate={gate_kind}>{gate_thresh:.2f} wrap={neut_wrap} | "
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
        if res.turnover > 0.5:
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
