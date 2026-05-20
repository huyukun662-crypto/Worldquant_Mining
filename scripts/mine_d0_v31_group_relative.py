"""v31 — group-relative structure: cross-sectional signals computed WITHIN
industry/subindustry peer groups instead of globally.

New operator family (confirmed accessible this tier): group_rank, group_zscore,
group_neutralize, group_scale. New gate: hump(x, hump=t). This subspace is
orthogonal to the v30 global-rank multiplicative lineage, so any SH>=2.0 hit
should carry low self-correlation to the existing 17 accepted alphas.

Tier-blocked (verified, do not use): vector_neut, regression_neut,
ts_partial_corr, ts_co_skewness, ts_regression, ts_min/ts_max, FAST neut.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v31")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V31_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}

FIXED_SETTINGS = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON"
}

# Raw (un-ranked) signals — group ops are applied to these directly.
RAW = {
    "iv_skew":  "(implied_volatility_call_60 - implied_volatility_put_60)",
    "iv_d5":    "ts_delta(implied_volatility_mean_60, 5)",
    "snt":      "snt_value",
    "rev_10":   "(-1 * ts_zscore(returns, 10))",
}

GROUPS = ["industry", "subindustry", "sector"]


def _g(op, sig, g):
    return f"{op}({RAW[sig]}, {g})"


def variant(name, g, w1, w2, w3, w4):
    """All variants live in group-relative space (the new structure)."""
    if name == "grank_mult":
        # v30 multiplicative breakthrough, but in group-relative ranks
        return (f"{w1:.3f} * (({_g('group_rank','iv_skew',g)} + {_g('group_rank','iv_d5',g)}) "
                f"* {_g('group_rank','rev_10',g)}) + {w2:.3f} * {_g('group_rank','snt',g)}")
    if name == "grank_blend":
        return (f"{w1:.3f} * {_g('group_rank','iv_skew',g)} + {w2:.3f} * {_g('group_rank','snt',g)} "
                f"+ {w3:.3f} * {_g('group_rank','iv_d5',g)} + {w4:.3f} * {_g('group_rank','rev_10',g)}")
    if name == "gneut_blend":
        return (f"{w1:.3f} * {_g('group_neutralize','iv_skew',g)} + {w2:.3f} * {_g('group_neutralize','snt',g)} "
                f"+ {w3:.3f} * {_g('group_neutralize','iv_d5',g)} + {w4:.3f} * {_g('group_neutralize','rev_10',g)}")
    if name == "gzscore_blend":
        return (f"{w1:.3f} * {_g('group_zscore','iv_skew',g)} + {w2:.3f} * {_g('group_zscore','snt',g)} "
                f"+ {w3:.3f} * {_g('group_zscore','iv_d5',g)} + {w4:.3f} * {_g('group_zscore','rev_10',g)}")
    if name == "gneut_v30":
        # group-neutralize the exact v30 global-rank composite -> industry residual
        body = (f"{w1:.3f} * ((rank({RAW['iv_skew']}) + rank({RAW['iv_d5']})) "
                f"* rank({RAW['rev_10']})) + {w2:.3f} * rank({RAW['snt']})")
        return f"group_neutralize({body}, {g})"
    if name == "gzscore_mult":
        return (f"{w1:.3f} * (({_g('group_zscore','iv_skew',g)} + {_g('group_zscore','iv_d5',g)}) "
                f"* {_g('group_zscore','rev_10',g)}) + {w2:.3f} * {_g('group_zscore','snt',g)}")
    raise ValueError(name)


VARIANTS = ["grank_mult", "grank_blend", "gneut_blend", "gzscore_blend",
            "gneut_v30", "gzscore_mult"]
GATES = ["news", "hump", "none"]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def append_result(rec):
    if RESULTS_FILE.exists():
        try: data = json.loads(RESULTS_FILE.read_text())
        except: data = []
    else: data = []
    data.append(rec); RESULTS_FILE.write_text(json.dumps(data, indent=2))


def build_expression(var_name, g, w1, w2, w3, w4, decay_n, gate, gate_p, wins_std):
    body = variant(var_name, g, w1, w2, w3, w4)
    inner = f"ts_decay_linear({body}, {decay_n})"
    if gate == "news":
        cond = f"(ts_rank(abs(news_pct_30min), 60) > {gate_p:.3f})"
        inner = f"trade_when({cond}, {inner}, -1)"
    elif gate == "hump":
        inner = f"hump({inner}, hump={gate_p:.3f})"
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
    ap.add_argument("--trials", type=int, default=250)
    ap.add_argument("--seed", type=int, default=31313)
    args = ap.parse_args()

    cm_mod = _load(VENDOR/"core"/"credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=20)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed: each variant x group x gate at a sane base
    for v in VARIANTS:
        for g in ["subindustry", "industry"]:
            for gate in ["news", "hump"]:
                study.enqueue_trial({
                    "variant": v, "group": g, "gate": gate,
                    "w1": 1.80, "w2": 0.90, "w3": 1.10, "w4": 0.40,
                    "decay_n": 28, "gate_p": (0.15 if gate == "news" else 0.01),
                    "wins_std": 4, "decay": 10, "truncation": 0.08,
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
        g = trial.suggest_categorical("group", GROUPS)
        gate = trial.suggest_categorical("gate", GATES)
        w1 = trial.suggest_float("w1", 1.00, 2.50)
        w2 = trial.suggest_float("w2", 0.40, 1.30)
        w3 = trial.suggest_float("w3", 0.70, 1.60)
        w4 = trial.suggest_float("w4", 0.20, 0.90)
        decay_n = trial.suggest_int("decay_n", 18, 35)
        gate_p = trial.suggest_float("gate_p", 0.005, 0.30)
        wins_std = trial.suggest_int("wins_std", 3, 5)
        decay = trial.suggest_categorical("decay", [8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08])
        neut = trial.suggest_categorical("neut", ["INDUSTRY", "SUBINDUSTRY"])

        settings = dict(FIXED_SETTINGS, universe="TOP3000", decay=decay,
                        truncation=truncation, neutralization=neut)
        expr = build_expression(var, g, w1, w2, w3, w4, decay_n, gate, gate_p, wins_std)
        log.info(f"t{trial.number}: var={var} grp={g} gate={gate}>{gate_p:.3f} "
                 f"w={w1:.2f}/{w2:.2f}/{w3:.2f}/{w4:.2f} N={decay_n} "
                 f"wins={wins_std} tr={truncation} dec={decay} neut={neut}")
        ekey = str((expr, "TOP3000", 0, decay, truncation, neut))
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
