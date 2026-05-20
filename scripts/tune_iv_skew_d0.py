"""Parameter sweep for the bare IV-skew D0 signal:

    group_zscore(implied_volatility_call_T - implied_volatility_put_T, GROUP)

Tunes (code)   : tenor T, group GROUP
Tunes (setting): decay, truncation, neutralization, universe
Fixed          : USA, delay=0, FASTEXPR, pasteurization=ON

For each combo: submit to WQ, record SH/FIT/TO/checks. For SH>=1.90 also
poll /correlations/self so we know which combos are decorrelated (<0.70)
against the existing submitted pool. Does NOT auto-submit — reports only.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ivtune")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_IVSKEW_TUNE_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}
SELF_CORR_MAX = 0.70

FIXED_SETTINGS = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON"
}

TENORS = [10, 20, 30, 90, 120, 150, 180]
GROUPS = ["industry", "subindustry", "sector"]
DECAYS = [0, 4, 6, 8, 10, 12, 16]
TRUNCS = [0.02, 0.05, 0.08, 0.10]
NEUTS = ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"]
UNIS = ["TOP3000", "TOP1000"]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def append_result(rec):
    if RESULTS_FILE.exists():
        try: data = json.loads(RESULTS_FILE.read_text())
        except: data = []
    else: data = []
    data.append(rec); RESULTS_FILE.write_text(json.dumps(data, indent=2))


def build_expression(tenor, g):
    skew = f"(implied_volatility_call_{tenor} - implied_volatility_put_{tenor})"
    return f"group_zscore({skew}, {g})"


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


def self_corr_max(session, alpha_id, tries=18, wait=8):
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self"
    for _ in range(tries):
        try:
            r = session.get(url, timeout=30)
        except Exception:
            time.sleep(wait); continue
        if r.status_code == 200 and r.text.strip():
            try:
                return r.json().get("max")
            except Exception:
                pass
        time.sleep(wait)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--seed", type=int, default=2020)
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

    # Seed: the exact config from the screenshot, then sweep tenor x group at it.
    for t in TENORS:
        for g in GROUPS:
            study.enqueue_trial({"tenor": t, "group": g, "decay": 10,
                                 "truncation": 0.08, "neut": "INDUSTRY",
                                 "universe": "TOP3000"})

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
        tenor = trial.suggest_categorical("tenor", TENORS)
        g = trial.suggest_categorical("group", GROUPS)
        decay = trial.suggest_categorical("decay", DECAYS)
        truncation = trial.suggest_categorical("truncation", TRUNCS)
        neut = trial.suggest_categorical("neut", NEUTS)
        universe = trial.suggest_categorical("universe", UNIS)

        settings = dict(FIXED_SETTINGS, universe=universe, decay=decay,
                        truncation=truncation, neutralization=neut)
        expr = build_expression(tenor, g)
        log.info(f"t{trial.number}: skew_{tenor}/{g} dec={decay} tr={truncation} "
                 f"neut={neut} uni={universe}")
        ekey = str((expr, universe, 0, decay, truncation, neut))
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

        self_corr = None
        if res.ok:
            log.info(f"  SH={res.sharpe:+.3f} FIT={res.fitness:+.3f} TO={res.turnover:.3f} "
                     f"chk={res.checks_passed}/{res.checks_total} alpha={res.alpha_id}")
            if res.sharpe >= 1.90 and res.alpha_id:
                self_corr = self_corr_max(session, res.alpha_id)
                rec["self_corr_max"] = self_corr
                log.info(f"  self_corr_max={self_corr}")
            if res.alpha_id and res.alpha_id not in seen_alphas:
                seen_alphas.add(res.alpha_id)
                ra = session.get(f"https://api.worldquantbrain.com/alphas/{res.alpha_id}", timeout=30)
                if ra.status_code == 200:
                    passed, fails = evaluate_pass(ra.json())
                    rec["all_pass"] = passed; rec["failure_reasons"] = fails
                    submittable = passed and (self_corr is not None) and (self_corr < SELF_CORR_MAX)
                    if submittable:
                        log.info(f"  *** PASS + DECORRELATED (corr={self_corr:.4f}) — submittable ***")
                    elif passed and self_corr is not None:
                        log.info(f"  pass IS but corr={self_corr:.4f} >= {SELF_CORR_MAX}")
                    elif passed:
                        log.info(f"  pass IS, corr unmeasured")
                    else:
                        log.info(f"  fails: {fails[:3]}")
        else:
            log.info(f"  [{res.error[:120]}]")

        append_result(rec)
        if not res.ok: return -10.0
        if res.turnover > 0.70: return res.sharpe - 2.0
        score = res.sharpe + 0.1*res.fitness + (res.checks_passed - 4)*0.5
        if self_corr is not None and self_corr > 0.50:
            score -= 4.0 * (self_corr - 0.50)
        return score

    try:
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    sys.exit(main())
