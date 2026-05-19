"""v30 — multiplicative legs: rank(A) * rank(B) or signed_power amplification.

Instead of pure addition across 4 legs, use multiplication on 1 or 2 pairs.
Alpha101 alphas that achieved SH > 2 commonly use rank(X)*rank(Y) to amplify
co-directional signal while damping anti-directional. Test 4 structural variants.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v30")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V30_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}

FIXED_SETTINGS = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON"
}

LEG1 = "rank(implied_volatility_call_60 - implied_volatility_put_60)"
LEG2 = "rank(snt_value)"
LEG3 = "rank(ts_delta(implied_volatility_mean_60, 5))"
LEG4 = "rank(-1 * ts_zscore(returns, 10))"

# Structural variants
def variant(name, w1, w2, w3, w4):
    if name == "L1xL3_add_L2L4":
        # iv_skew * iv_mean_d5 + snt + rev_10 (option*option_delta interaction)
        return f"{w1:.3f} * ({LEG1} * {LEG3}) + {w2:.3f} * {LEG2} + {w4:.3f} * {LEG4}"
    if name == "L1xL2_add_L3L4":
        # iv_skew * snt + iv_mean_d5 + rev_10 (option*sentiment interaction)
        return f"{w1:.3f} * ({LEG1} * {LEG2}) + {w3:.3f} * {LEG3} + {w4:.3f} * {LEG4}"
    if name == "L1sp2_add_others":
        # signed_power(L1, 2) emphasizes large iv_skew + rest
        return (f"{w1:.3f} * signed_power({LEG1}, 2) + {w2:.3f} * {LEG2} "
                f"+ {w3:.3f} * {LEG3} + {w4:.3f} * {LEG4}")
    if name == "L1xL3_sp_add":
        # signed_power(L1*L3, 1.5) -- amplified option interaction
        return (f"{w1:.3f} * signed_power({LEG1} * {LEG3}, 1.5) "
                f"+ {w2:.3f} * {LEG2} + {w4:.3f} * {LEG4}")
    if name == "L1L3_div_L4":
        # (iv_skew + iv_mean_d5) * rev_10 -- option group amplified by reversal
        return (f"{w1:.3f} * (({LEG1} + {LEG3}) * {LEG4}) + {w2:.3f} * {LEG2}")
    if name == "all4_add_L3L4":
        # all 4 added but with L3*L4 cross-term
        return (f"{w1:.3f} * {LEG1} + {w2:.3f} * {LEG2} + {w3:.3f} * {LEG3} "
                f"+ {w4:.3f} * ({LEG3} * {LEG4})")
    raise ValueError(name)


VARIANTS = ["L1xL3_add_L2L4", "L1xL2_add_L3L4", "L1sp2_add_others",
            "L1xL3_sp_add", "L1L3_div_L4", "all4_add_L3L4"]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def append_result(rec):
    if RESULTS_FILE.exists():
        try: data = json.loads(RESULTS_FILE.read_text())
        except: data = []
    else: data = []
    data.append(rec); RESULTS_FILE.write_text(json.dumps(data, indent=2))


def build_expression(var_name, w1, w2, w3, w4, decay_n, gate_thresh, wins_std):
    body = variant(var_name, w1, w2, w3, w4)
    inner = f"ts_decay_linear({body}, {decay_n})"
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
    ap.add_argument("--seed", type=int, default=30303)
    args = ap.parse_args()

    cm_mod = _load(VENDOR/"core"/"credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=12)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed each variant at v27 base
    for v in VARIANTS:
        study.enqueue_trial({
            "variant": v, "w1": 1.90, "w2": 0.96, "w3": 1.15, "w4": 0.39,
            "decay_n": 26, "gate_thresh": 0.186, "wins_std": 4,
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
        var = trial.suggest_categorical("variant", VARIANTS)
        w1 = trial.suggest_float("w1", 1.00, 2.50)
        w2 = trial.suggest_float("w2", 0.50, 1.30)
        w3 = trial.suggest_float("w3", 0.80, 1.60)
        w4 = trial.suggest_float("w4", 0.20, 0.80)
        decay_n = trial.suggest_int("decay_n", 18, 35)
        gate_thresh = trial.suggest_float("gate_thresh", 0.10, 0.30)
        wins_std = trial.suggest_int("wins_std", 3, 5)
        decay = trial.suggest_categorical("decay", [8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.03, 0.05, 0.08])

        settings = dict(FIXED_SETTINGS, universe="TOP3000", decay=decay,
                        truncation=truncation, neutralization="INDUSTRY")
        expr = build_expression(var, w1, w2, w3, w4, decay_n, gate_thresh, wins_std)
        log.info(f"t{trial.number}: var={var} w={w1:.2f}/{w2:.2f}/{w3:.2f}/{w4:.2f} "
                 f"N={decay_n} gate>{gate_thresh:.2f} wins={wins_std} tr={truncation} dec={decay}")
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
