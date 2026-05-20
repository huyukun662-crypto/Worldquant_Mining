"""v34 — NEW SIGNAL FAMILY for a decorrelated D0 alpha: earnings-estimate
revisions, analyst dispersion, and EV/EBITDA value.

WHY: 33 prior versions exhausted IV-skew (the only USA-D0 SH>=2.0 signal we
had), but every variant self-correlates >0.70 with the active akN9pwQw, so no
second alpha is submittable from that family. IV-skew + the mdl177 model fields
are USA-only / D1-only, so a region pivot is impossible. HOWEVER USA D0 exposes
large UNMINED families: analyst estimates (anl4, 2115 fields), earnings
estimates (est_*, 2051), fundamentals (1123). These are a DIFFERENT data series
from IV-skew -> structurally decorrelated from the existing pool.

STRUCTURE: reuse the proven akN9pwQw wrapper — group_zscore blend (strips units,
so unit-safe under VERIFY), ts_decay_linear smoothing, optional news-gate,
winsorize for CONCENTRATED_WEIGHT — but the dominant leg is a TPE-chosen
earnings/analyst/value signal. Sparse estimate fields are ts_backfill'd. After
each SH>=1.90 hit we measure /correlations/self; a candidate is flagged
SUBMITTABLE only if it passes all is.checks AND has a MEASURED corr < 0.70.
Does NOT auto-submit — surfaces candidates for the user to submit.

D0 check bars (this account): LOW_SHARPE>=2.0, LOW_FITNESS>=1.3, HIGH_TURNOVER<=0.70.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v34")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V34_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}
SELF_CORR_MAX = 0.70

FIXED_SETTINGS = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON"
}

BF = 120  # ts_backfill window for sparse estimate/fundamental fields
GROUPS = ["industry", "subindustry", "sector"]
GATES = ["news", "none"]

# Stabilizer legs (small weight; both unit-safe pre-group_zscore).
SNT = "snt_value"
REV = "(-1 * ts_zscore(returns, 10))"


def _bf(field):
    return f"ts_backfill({field}, {BF})"


def signal_expr(name, n):
    """Dominant raw leg. All ratio/delta forms are unit-safe; group_zscore
    (applied by build_expression) strips units regardless."""
    if name == "ev_ebitda":              # value: cheap (low EV/EBITDA) scores high
        return f"(-1 * {_bf('enterprise_value')} / {_bf('ebitda')})"
    if name == "earn_rev_ebitda":        # estimate revision momentum
        return f"ts_delta({_bf('est_ebitda')}, {n})"
    if name == "earn_rev_eps":
        return f"ts_delta({_bf('est_epsr')}, {n})"
    if name == "earn_rev_netprofit":
        return f"ts_delta({_bf('est_netprofit')}, {n})"
    if name == "anl_rev":                # current vs previous consensus estimate
        cur = _bf("anl4_fs_detail_estimate_basic_af_v4_estimate")
        prev = _bf("anl4_fs_detail_estimate_basic_af_v4_previosestimate")
        return f"({cur} / {prev} - 1)"
    if name == "earn_surprise":          # actual vs estimate (SUE-like), ratio form
        return f"({_bf('actual_eps_value')} / {_bf('est_epsr')} - 1)"
    if name == "anl_disp":               # low analyst disagreement scores high
        hi = _bf("anl4_basicconaf_high"); lo = _bf("anl4_basicconaf_low")
        return f"(-1 * ({hi} - {lo}))"
    if name == "sales_growth_mom":
        return f"ts_delta({_bf('sales_growth')}, {n})"
    raise ValueError(name)


SIGNALS = ["ev_ebitda", "earn_rev_ebitda", "earn_rev_eps", "earn_rev_netprofit",
           "anl_rev", "earn_surprise", "anl_disp", "sales_growth_mom"]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def append_result(rec):
    if RESULTS_FILE.exists():
        try: data = json.loads(RESULTS_FILE.read_text())
        except: data = []
    else: data = []
    data.append(rec); RESULTS_FILE.write_text(json.dumps(data, indent=2))


def build_expression(sig, g, w1, w2, w3, n, decay_n, gate, gate_p, wins_std):
    raw = signal_expr(sig, n)
    body = (f"{w1:.3f} * group_zscore({raw}, {g}) "
            f"+ {w2:.3f} * group_zscore({SNT}, {g}) "
            f"+ {w3:.3f} * group_zscore({REV}, {g})")
    inner = f"ts_decay_linear({body}, {decay_n})"
    if gate == "news":
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
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed", type=int, default=34343)
    args = ap.parse_args()

    cm_mod = _load(VENDOR/"core"/"credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=24)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed: each signal family x {news,none} at a sane base, sector group.
    for sig in SIGNALS:
        for gate in GATES:
            study.enqueue_trial({
                "signal": sig, "group": "sector", "gate": gate,
                "w1": 1.80, "w2": 0.50, "w3": 0.30,
                "n": 20, "decay_n": 20, "gate_p": 0.12, "wins_std": 4,
                "decay": 8, "truncation": 0.08,
                "neut": "INDUSTRY", "universe": "TOP3000",
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
        sig = trial.suggest_categorical("signal", SIGNALS)
        g = trial.suggest_categorical("group", GROUPS)
        gate = trial.suggest_categorical("gate", GATES)
        w1 = trial.suggest_float("w1", 1.20, 2.30)
        w2 = trial.suggest_float("w2", 0.10, 0.90)
        w3 = trial.suggest_float("w3", 0.10, 0.70)
        n = trial.suggest_int("n", 5, 60)
        decay_n = trial.suggest_int("decay_n", 12, 40)
        gate_p = trial.suggest_float("gate_p", 0.05, 0.25)
        wins_std = trial.suggest_int("wins_std", 3, 5)
        decay = trial.suggest_categorical("decay", [4, 8, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08])
        neut = trial.suggest_categorical("neut", ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"])
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])

        settings = dict(FIXED_SETTINGS, universe=universe, decay=decay,
                        truncation=truncation, neutralization=neut)
        expr = build_expression(sig, g, w1, w2, w3, n, decay_n, gate, gate_p, wins_std)
        log.info(f"t{trial.number}: {sig}/{g} gate={gate} w={w1:.2f}/{w2:.2f}/{w3:.2f} "
                 f"n={n} N={decay_n} wins={wins_std} tr={truncation} dec={decay} "
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
                        log.info(f"  *** SUBMITTABLE: PASS + DECORRELATED (corr={self_corr:.4f}) "
                                 f"alpha={res.alpha_id} — NOT auto-submitting, surfacing ***")
                    elif passed and self_corr is not None:
                        log.info(f"  pass IS but corr={self_corr:.4f} >= {SELF_CORR_MAX}")
                    elif passed:
                        log.info(f"  pass IS, corr unmeasured")
                    else:
                        log.info(f"  fails: {fails[:3]}")
        else:
            log.info(f"  [{res.error[:140]}]")

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
