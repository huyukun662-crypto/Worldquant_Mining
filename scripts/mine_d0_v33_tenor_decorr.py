"""v33 — strong-AND-decorrelated D0 via IV-skew TENOR diversity.

KEY FINDING: implied-vol skew (call_T - put_T) is individually strong at EVERY
tenor — group_zscore(call_T-put_T, sector) alone scores SH 2.17-2.24 for
T in {10,20,30,90,120,150,180} (no decay/gate). Each tenor is a DIFFERENT data
series, so their PnL differs — giving a shot at <0.70 self-correlation against
the existing _60 alpha family WITHOUT diluting Sharpe (the v32 mistake: mixing in
weak PV signals dragged SH to ~1.6).

STRUCTURE: the proven v31 chk=7 recipe — group_zscore blend, news-gated,
decay-smoothed, winsorized — but the dominant leg is iv_skew at a TPE-chosen
tenor, and universe/neutralization are extra decorrelation levers. After each
chk>=7 hit we query /correlations/self and only submit when max-corr < 0.68;
the objective penalizes self-correlation to steer toward the decorrelated frontier.

Tier facts: skew tenors 10..180 OK (250 absent). Groups industry/subindustry/
sector OK. Blocked: ts_skewness/kurtosis, pcr_oi_60, vector_neut, ts_min/max.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v33")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V33_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}
SELF_CORR_MAX = 0.69   # WQ submission cutoff is 0.70; 0.01 measurement margin

FIXED_SETTINGS = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON"
}

TENORS = [10, 20, 30, 90, 120, 150, 180]
GROUPS = ["industry", "subindustry", "sector"]
# small stabilizer legs (low weight; same as v31's minor legs)
SNT = "snt_value"
REV = "(-1 * ts_zscore(returns, 10))"


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def append_result(rec):
    if RESULTS_FILE.exists():
        try: data = json.loads(RESULTS_FILE.read_text())
        except: data = []
    else: data = []
    data.append(rec); RESULTS_FILE.write_text(json.dumps(data, indent=2))


def build_expression(tenor, g, w1, w2, w3, decay_n, gate_p, wins_std):
    skew = f"(implied_volatility_call_{tenor} - implied_volatility_put_{tenor})"
    body = (f"{w1:.3f} * group_zscore({skew}, {g}) "
            f"+ {w2:.3f} * group_zscore({SNT}, {g}) "
            f"+ {w3:.3f} * group_zscore({REV}, {g})")
    inner = f"ts_decay_linear({body}, {decay_n})"
    cond = f"(ts_rank(abs(news_pct_30min), 60) > {gate_p:.3f})"
    inner = f"trade_when({cond}, {inner}, -1)"
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


def self_corr_max(session, alpha_id, tries=20, wait=8):
    """Poll /correlations/self. The endpoint computes asynchronously: the first
    GET triggers computation and returns empty; later GETs return data once ready.
    Returns max correlation, or None if it never populates (caller must NOT treat
    None as decorrelated)."""
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


def attempt_submit(session, alpha_id):
    sa_mod = _load(REPO/"scripts"/"submit_alpha.py", "sa")
    return sa_mod.submit_alpha(session, alpha_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed", type=int, default=33333)
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

    # Seed: sweep tenors across the decorrelation levers (neutralization + universe).
    # At INDUSTRY/TOP3000 only skew_20 dropped below 0.70 — the far tenors need a
    # different neut/universe to shift their PnL away from the existing _60 family.
    lever_combos = [("SUBINDUSTRY", "TOP3000"), ("MARKET", "TOP3000"),
                    ("SECTOR", "TOP3000"), ("INDUSTRY", "TOP1000")]
    for t in TENORS:
        for neut, uni in lever_combos:
            study.enqueue_trial({
                "tenor": t, "group": "sector",
                "w1": 1.80, "w2": 0.90, "w3": 0.40,
                "decay_n": 30, "gate_p": 0.12, "wins_std": 4,
                "decay": 12, "truncation": 0.05,
                "neut": neut, "universe": uni,
            })

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
        w1 = trial.suggest_float("w1", 1.20, 2.30)
        w2 = trial.suggest_float("w2", 0.20, 1.20)
        w3 = trial.suggest_float("w3", 0.10, 0.80)
        decay_n = trial.suggest_int("decay_n", 18, 35)
        gate_p = trial.suggest_float("gate_p", 0.05, 0.25)
        wins_std = trial.suggest_int("wins_std", 3, 5)
        decay = trial.suggest_categorical("decay", [8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08])
        neut = trial.suggest_categorical("neut", ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"])
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])

        settings = dict(FIXED_SETTINGS, universe=universe, decay=decay,
                        truncation=truncation, neutralization=neut)
        expr = build_expression(tenor, g, w1, w2, w3, decay_n, gate_p, wins_std)
        log.info(f"t{trial.number}: skew_{tenor}/{g} w={w1:.2f}/{w2:.2f}/{w3:.2f} "
                 f"N={decay_n} gate>{gate_p:.2f} wins={wins_std} tr={truncation} "
                 f"dec={decay} neut={neut} uni={universe}")
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
                    # require a MEASURED correlation below threshold; never treat
                    # an unmeasurable (None) correlation as decorrelated.
                    decorrelated = (self_corr is not None) and (self_corr < SELF_CORR_MAX)
                    if passed and decorrelated:
                        log.info(f"  *** PASSED + DECORRELATED (corr={self_corr:.4f}) — submitting ***")
                        sub = attempt_submit(session, res.alpha_id)
                        rec["submit_response"] = sub
                        if sub.get("ok"):
                            log.info(f"  *** SUBMIT POSTED: {res.alpha_id} (verify ACTIVE) ***")
                    elif passed and self_corr is None:
                        log.info(f"  passed IS but self_corr unmeasured — NOT submitting")
                    elif passed:
                        log.info(f"  passed IS but self_corr={self_corr:.4f} >= {SELF_CORR_MAX} — NOT submitting")
                    else:
                        log.info(f"  fails: {fails[:3]}")
        else:
            log.info(f"  [{res.error[:120]}]")

        append_result(rec)
        if not res.ok: return -10.0
        if res.turnover > 0.50: return res.sharpe - 2.0
        score = res.sharpe + 0.1*res.fitness + (res.checks_passed - 4)*0.5
        if self_corr is not None and self_corr > 0.50:
            score -= 4.0 * (self_corr - 0.50)   # strongly steer toward decorrelated
        return score

    try:
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    sys.exit(main())
