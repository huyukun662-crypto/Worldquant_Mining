"""D0 v22 — PURE SENTIMENT / NEWS only, no PV, no option, no fundamentals.

User spec: "纯sentiment不要混合". This is the sentiment-only branch.

Available fields:
  - snt_value, snt_buzz (sentiment/socialmedia)
  - news_pct_30min, news_pct_90min (news intensity)

Signal library: 16 sentiment/news-only signals across:
  - Sentiment level + transforms (rank, ts_zscore, ts_delta)
  - Buzz level + transforms
  - Snt-buzz product (intensity weighted)
  - News intensity (30/90, abs, z-score)
  - News term-structure (90 - 30)
  - Trade_when news gate optional (since news IS sentiment family)

The chk=6 v11 family used snt_value as a LEG combined with iv_skew.
Here we strip option entirely and rely only on sentiment+news to
generate the alpha. Realistic ceiling unknown — sentiment alone has
weaker stand-alone alpha than iv_skew.
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
log = logging.getLogger("mine-v22")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V22_RESULTS.json"
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

SENT_SIGNALS: dict[str, str] = {
    # Sentiment level
    "snt":         "rank(snt_value)",
    "snt_n":       "rank(-1 * snt_value)",
    "snt_z5":      "rank(ts_zscore(snt_value, 5))",
    "snt_z20":     "rank(ts_zscore(snt_value, 20))",
    "snt_z60":     "rank(ts_zscore(snt_value, 60))",
    "snt_d5":      "rank(ts_delta(snt_value, 5))",
    "snt_residual": "rank(snt_value - ts_mean(snt_value, 60))",
    # Buzz
    "buzz":        "rank(snt_buzz)",
    "buzz_z":      "rank(ts_zscore(snt_buzz, 20))",
    # Sentiment x buzz (intensity-weighted)
    "snt_buzz":    "rank(snt_value * snt_buzz)",
    "snt_buzz_z":  "rank(ts_zscore(snt_value * snt_buzz, 20))",
    # News intensity
    "news30":      "rank(news_pct_30min)",
    "news90":      "rank(news_pct_90min)",
    "news_abs_z":  "rank(ts_zscore(abs(news_pct_30min), 60))",
    "news_term":   "rank(news_pct_90min - news_pct_30min)",
    "news_term_n": "rank(news_pct_30min - news_pct_90min)",
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


def build_expression(sigs: list[str], weights: list[float],
                     decay_n: int, neut_wrap: str,
                     gate_kind: str, gate_thresh: float) -> str:
    parts = [f"{w:.2f} * {SENT_SIGNALS[s]}" for s, w in zip(sigs, weights)]
    body = " + ".join(parts)
    inner = f"ts_decay_linear({body}, {decay_n})"
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
    ap.add_argument("--seed", type=int, default=22222)
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

    sig_names = list(SENT_SIGNALS)

    # Seeds: each single-leg signal
    for s in sig_names:
        study.enqueue_trial({
            "sig1_idx": sig_names.index(s), "sig2_idx": -1, "sig3_idx": -1,
            "w1": 1.0, "w2": 0.5, "w3": 0.3, "decay_n": 5,
            "neut_wrap": "none", "gate_kind": "none", "gate_thresh": 0.6,
            "universe": "TOP3000", "decay": 4, "truncation": 0.08,
            "neutralization": "INDUSTRY",
        })
    # Also try snt_value+news_or gate at v11-style decay
    study.enqueue_trial({
        "sig1_idx": sig_names.index("snt"), "sig2_idx": -1, "sig3_idx": -1,
        "w1": 1.0, "w2": 0.5, "w3": 0.3, "decay_n": 35,
        "neut_wrap": "none", "gate_kind": "news_or", "gate_thresh": 0.60,
        "universe": "TOP3000", "decay": 8, "truncation": 0.08,
        "neutralization": "INDUSTRY",
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
