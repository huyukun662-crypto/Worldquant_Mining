"""v29 — stacked max/min: outer = max/min of TWO ts_rank(ts_decay_linear) branches.

Branch A: the v27 winning 4-leg blend.
Branch B: a TPE-chosen alternative signal.
Outer joins them via max | min | average.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v29")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V29_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}

FIXED_SETTINGS = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON"
}

# Branch A (v27 winning 4-leg blend, parametrized weights)
BR_A_LEGS = [
    "rank(implied_volatility_call_60 - implied_volatility_put_60)",
    "rank(snt_value)",
    "rank(ts_delta(implied_volatility_mean_60, 5))",
    "rank(-1 * ts_zscore(returns, 10))",
]

# Branch B candidates — single signal each
BR_B = {
    "iv_term":      "rank(implied_volatility_mean_60 - implied_volatility_mean_30)",
    "iv_vs_hv":     "rank(implied_volatility_mean_60 - historical_volatility_60)",
    "iv_skew_z":    "rank(ts_zscore(implied_volatility_call_60 - implied_volatility_put_60, 20))",
    "snt_z20":      "rank(ts_zscore(snt_value, 20))",
    "snt_buzz":     "rank(snt_value * snt_buzz)",
    "rev_5":        "rank(-1 * ts_zscore(returns, 5))",
    "rev_20":       "rank(-1 * ts_zscore(returns, 20))",
    "pv_corr_n":    "rank(-1 * ts_corr(close, volume, 30))",
    "a040":         "(-1 * rank(ts_std_dev(high, 10))) * ts_corr(high, volume, 20)",
    "skew_neg":     "rank(-1 * ts_skewness(returns, 60))",
    "vwap_dev":     "rank((close - vwap) / (vwap + 0.01))",
    "argmax_dist":  "rank((20 - ts_arg_max(close, 20)) / 20)",
}


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def append_result(rec):
    if RESULTS_FILE.exists():
        try: data = json.loads(RESULTS_FILE.read_text())
        except: data = []
    else: data = []
    data.append(rec); RESULTS_FILE.write_text(json.dumps(data, indent=2))


def build_expression(sig_b, w_a, w_b,
                     wA1, wA2, wA3, wA4,
                     decay_a, decay_b, rank_a, rank_b,
                     outer_op, gate_thresh, wins_std):
    branch_a_body = (f"{wA1:.3f} * {BR_A_LEGS[0]} + {wA2:.3f} * {BR_A_LEGS[1]} "
                     f"+ {wA3:.3f} * {BR_A_LEGS[2]} + {wA4:.3f} * {BR_A_LEGS[3]}")
    branch_a = f"ts_rank(ts_decay_linear({branch_a_body}, {decay_a}), {rank_a})"
    branch_b = f"ts_rank(ts_decay_linear({BR_B[sig_b]}, {decay_b}), {rank_b})"
    if outer_op == "max":
        inner = f"max({w_a:.3f} * {branch_a}, {w_b:.3f} * {branch_b})"
    elif outer_op == "min":
        inner = f"min({w_a:.3f} * {branch_a}, {w_b:.3f} * {branch_b})"
    else:  # avg
        inner = f"({w_a:.3f} * {branch_a} + {w_b:.3f} * {branch_b}) / 2"
    gate = f"(ts_rank(abs(news_pct_30min), 60) > {gate_thresh:.3f})"
    inner = f"trade_when({gate}, {inner}, -1)"
    return f"winsorize({inner}, std={wins_std})"


def evaluate_pass(alpha_json):
    fails = []
    checks = (alpha_json.get("is") or {}).get("checks") or []
    if not checks: return False, ["no is.checks returned"]
    for c in checks:
        n=c.get("name","?"); r=c.get("result","?")
        if r=="PASS": continue
        if r=="PENDING" and n in SELF_CORR_PENDING_OK: continue
        fails.append(f"{n}={r} (limit={c.get('limit')}, value={c.get('value')})")
    return len(fails)==0, fails


def attempt_submit(session, alpha_id):
    sa_mod = _load(REPO/"scripts"/"submit_alpha.py", "sa")
    return sa_mod.submit_alpha(session, alpha_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--seed", type=int, default=29292)
    args = ap.parse_args()

    cm_mod = _load(VENDOR/"core"/"credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=18)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed each branch-B candidate at sane defaults
    for s in BR_B:
        for op in ["max", "avg"]:
            study.enqueue_trial({
                "sig_b": s, "outer_op": op,
                "w_a": 1.0, "w_b": 0.5,
                "wA1": 1.90, "wA2": 0.96, "wA3": 1.15, "wA4": 0.39,
                "decay_a": 26, "decay_b": 20, "rank_a": 20, "rank_b": 20,
                "gate_thresh": 0.186, "wins_std": 4,
                "decay": 10, "truncation": 0.05,
            })

    found = {"alpha_id": None}
    seen_alphas = set(); seen_exprs = {}
    if RESULTS_FILE.exists():
        try:
            for x in json.loads(RESULTS_FILE.read_text()):
                if x.get("ok") and x.get("alpha_id"): seen_alphas.add(x["alpha_id"])
                s=x.get("settings",{})
                key=(x.get("expression",""), s.get("universe"), s.get("delay"), s.get("decay"),
                     s.get("truncation"), s.get("neutralization"))
                if x.get("expression"): seen_exprs[str(key)] = x.get("alpha_id","?")
        except: pass
    log.info(f"resume: {len(seen_alphas)} alpha_ids, {len(seen_exprs)} skip-list")

    def objective(trial):
        sig_b = trial.suggest_categorical("sig_b", list(BR_B))
        outer_op = trial.suggest_categorical("outer_op", ["max", "min", "avg"])
        w_a = trial.suggest_float("w_a", 0.5, 2.0)
        w_b = trial.suggest_float("w_b", 0.3, 1.5)
        wA1 = trial.suggest_float("wA1", 1.50, 2.10)
        wA2 = trial.suggest_float("wA2", 0.70, 1.20)
        wA3 = trial.suggest_float("wA3", 0.90, 1.40)
        wA4 = trial.suggest_float("wA4", 0.20, 0.55)
        decay_a = trial.suggest_int("decay_a", 15, 35)
        decay_b = trial.suggest_int("decay_b", 10, 35)
        rank_a = trial.suggest_int("rank_a", 10, 40)
        rank_b = trial.suggest_int("rank_b", 10, 40)
        gate_thresh = trial.suggest_float("gate_thresh", 0.10, 0.30)
        wins_std = trial.suggest_int("wins_std", 3, 5)
        decay = trial.suggest_categorical("decay", [8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.03, 0.05, 0.08])

        settings = dict(FIXED_SETTINGS, universe="TOP3000", decay=decay,
                        truncation=truncation, neutralization="INDUSTRY")
        expr = build_expression(sig_b, w_a, w_b, wA1, wA2, wA3, wA4,
                                 decay_a, decay_b, rank_a, rank_b,
                                 outer_op, gate_thresh, wins_std)
        log.info(f"t{trial.number}: B={sig_b}({outer_op}) wA/wB={w_a:.2f}/{w_b:.2f} "
                 f"dA/dB/rA/rB={decay_a}/{decay_b}/{rank_a}/{rank_b} "
                 f"gate>{gate_thresh:.2f} wins={wins_std} tr={truncation} dec={decay}")
        ekey = str((expr, "TOP3000", 0, decay, truncation, "INDUSTRY"))
        if ekey in seen_exprs:
            log.info(f"  (skip — already as {seen_exprs[ekey]})")
            return -5.0

        res = wq_submit(session, expr, settings)
        if res.ok and res.alpha_id: seen_exprs[ekey] = res.alpha_id

        rec = {"ts": time.time(), "trial": trial.number, "params": trial.params,
               "expression": expr, "settings": res.settings, "ok": res.ok,
               "alpha_id": res.alpha_id, "error": res.error,
               "sharpe": res.sharpe, "turnover": res.turnover, "fitness": res.fitness,
               "returns": res.returns, "drawdown": res.drawdown,
               "checks_passed": res.checks_passed, "checks_total": res.checks_total}
        if res.ok:
            log.info(f"  SH={res.sharpe:+.3f} FIT={res.fitness:+.3f} TO={res.turnover:.3f} "
                     f"chk={res.checks_passed}/{res.checks_total} alpha={res.alpha_id}")
            if res.alpha_id and res.alpha_id not in seen_alphas:
                seen_alphas.add(res.alpha_id)
                ra = session.get(f"https://api.worldquantbrain.com/alphas/{res.alpha_id}", timeout=30)
                if ra.status_code == 200:
                    passed, fails = evaluate_pass(ra.json())
                    rec["all_pass"] = passed; rec["failure_reasons"] = fails
                    if passed:
                        log.info("  *** PASSED — submitting ***")
                        sub = attempt_submit(session, res.alpha_id)
                        rec["submit_response"] = sub
                        if sub.get("ok"):
                            log.info(f"  *** SUBMIT ACCEPTED: {res.alpha_id} ***")
                            found["alpha_id"] = res.alpha_id
                    else:
                        log.info(f"  fails: {fails[:3]}")
        else:
            log.info(f"  [{res.error[:120]}]")

        append_result(rec)
        if not res.ok: return -10.0
        if res.turnover > 0.50: return res.sharpe - 2.0
        return res.sharpe + 0.1*res.fitness + (res.checks_passed - 4)*0.5

    try:
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    sys.exit(main())
