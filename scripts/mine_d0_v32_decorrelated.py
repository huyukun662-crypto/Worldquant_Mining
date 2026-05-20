"""v32 — decorrelated mining: orthogonal signal families + self-correlation gate.

WHY: every prior D0 alpha (v30 global-rank, v31 group-relative) shares the same
four signals — iv_skew (iv_call60-iv_put60), iv_mean_d5, snt_value, rev_10 — so
they all self-correlate 0.72-0.78 against each other. WQ's submission gate rejects
anything > 0.70 vs the existing pool, so only ONE alpha per family is submittable.
Different wrappers do not decorrelate outputs built from identical inputs.

FIX: (1) draw signals from families DELIBERATELY orthogonal to that quartet
(liquidity, intraday range, vwap, longer-horizon reversal/momentum, higher-moment
timing, argmax timing, put-call ratio, IV term-structure, IV-vs-HV, buzz, news90);
(2) after a chk>=7 hit, query /alphas/{id}/correlations/self and only treat it as a
real keeper / auto-submit when max self-corr < SELF_CORR_MAX. The objective also
penalizes high self-correlation so TPE actively seeks decorrelated structure.

Structure reuses the proven group_zscore blend (high fitness on this tier),
news-gated, decay-smoothed, winsorized. Group ops confirmed accessible:
group_zscore/group_rank/group_neutralize. Tier-blocked (do not use): vector_neut,
regression_neut, ts_partial_corr, ts_co_skewness, ts_regression, ts_min/ts_max.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v32")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V32_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}
SELF_CORR_MAX = 0.68   # submission gate is 0.70; keep margin

FIXED_SETTINGS = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON"
}

# Signal families DELIBERATELY orthogonal to {iv_skew, iv_mean_d5, snt_value, rev_10}.
# All resolve to unit-clean quantities: ratios are written as x/y-1 and volume/dollar
# signals are z-scored, so unitHandling=VERIFY does not flag constant-adds across legs.
RAW = {
    # liquidity / volume microstructure
    "illiq":     "(-1 * ts_corr(close, volume, 20))",
    "vol_surp":  "ts_zscore(volume / adv20, 20)",
    "dvol_mom":  "ts_zscore(close * volume, 20)",
    # intraday / range
    "intra":     "(close / open - 1)",
    "hl_range":  "(high / low - 1)",
    "gap":       "(open / ts_delay(close, 1) - 1)",
    # vwap
    "vwap_dev":  "(close / vwap - 1)",
    # longer-horizon reversal / momentum (different window than rev_10)
    "rev_60":    "(-1 * ts_zscore(returns, 60))",
    "mom_120":   "(close / ts_delay(close, 120) - 1)",
    # extrema / vol-regime timing (ts_skewness/ts_kurtosis are tier-blocked)
    "argmax":    "((20 - ts_arg_max(close, 20)) / 20)",
    "argmin":    "((20 - ts_arg_min(close, 20)) / 20)",
    "volregime": "ts_arg_max(ts_std_dev(returns, 20), 60)",
    # option family DIFFERENT from iv_skew / iv_mean_d5 (pcr_oi_60 not on tier)
    "iv_term":   "(implied_volatility_mean_60 - implied_volatility_mean_30)",
    "iv_vs_hv":  "(implied_volatility_mean_60 - historical_volatility_60)",
    "ivskew60":  "implied_volatility_mean_skew_60",
    # sentiment / news DIFFERENT from snt_value
    "buzz":      "snt_buzz",
    "news90":    "ts_zscore(abs(news_pct_90min), 60)",
    # the proven-strong quartet — included so TPE can BLEND strength with the
    # orthogonal signals above; the self-corr penalty forces enough orthogonal
    # content to clear the 0.70 gate while keeping enough signal to pass SH>=2.0.
    "iv_skew":   "(implied_volatility_call_60 - implied_volatility_put_60)",
    "iv_d5":     "ts_delta(implied_volatility_mean_60, 5)",
    "snt":       "snt_value",
    "rev_10":    "(-1 * ts_zscore(returns, 10))",
}
SIGS = list(RAW)
GROUPS = ["industry", "subindustry", "sector"]
# Only unit-stripping wraps: group_zscore and group_rank both output unitless
# values, so blends of united + unitless raw signals pass unitHandling=VERIFY.
# group_neutralize preserves the input unit and breaks mixed-unit blends.
WRAPS = ["gzscore", "grank"]
GOP = {"gzscore": "group_zscore", "grank": "group_rank"}

# Curated seed blends — mix one/two proven-strong signals with orthogonal ones
# to land near SH 2.0 while pulling self-correlation below the 0.70 gate.
SEED_BLENDS = [
    ("iv_skew", "illiq", "vwap_dev", "rev_60"),
    ("iv_skew", "ivskew60", "iv_term", "argmax"),
    ("snt", "illiq", "vol_surp", "intra"),
    ("iv_d5", "iv_vs_hv", "vwap_dev", "rev_60"),
    ("iv_skew", "buzz", "news90", "argmin"),
    ("rev_10", "iv_term", "volregime", "gap"),
    ("iv_skew", "rev_60", "ivskew60", "vwap_dev"),
    ("snt", "intra", "iv_vs_hv", "vol_surp"),
    ("iv_skew", "snt", "illiq", "ivskew60"),
    ("iv_d5", "rev_10", "mom_120", "hl_range"),
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def append_result(rec):
    if RESULTS_FILE.exists():
        try: data = json.loads(RESULTS_FILE.read_text())
        except: data = []
    else: data = []
    data.append(rec); RESULTS_FILE.write_text(json.dumps(data, indent=2))


def build_expression(wrap, g, sigs, ws, decay_n, gate, gate_p, wins_std):
    op = GOP[wrap]
    terms = " + ".join(f"{w:.3f} * {op}({RAW[s]}, {g})" for s, w in zip(sigs, ws))
    inner = f"ts_decay_linear({terms}, {decay_n})"
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


def self_corr_max(session, alpha_id, tries=8):
    """Poll /correlations/self (computed async) and return max correlation
    against the user's existing pool, or None if unavailable."""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self"
    for _ in range(tries):
        try:
            r = session.get(url, timeout=30)
        except Exception:
            time.sleep(5); continue
        if r.status_code == 200 and r.text.strip():
            try:
                j = r.json()
                return j.get("max")
            except Exception:
                return None
        time.sleep(5)
    return None


def attempt_submit(session, alpha_id):
    sa_mod = _load(REPO/"scripts"/"submit_alpha.py", "sa")
    return sa_mod.submit_alpha(session, alpha_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed", type=int, default=32323)
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

    # Seed curated diverse blends across wraps/groups
    for blend in SEED_BLENDS:
        for wrap in ["gzscore", "grank"]:
            study.enqueue_trial({
                "wrap": wrap, "group": "sector",
                "sig1": blend[0], "sig2": blend[1], "sig3": blend[2], "sig4": blend[3],
                "w1": 1.50, "w2": 1.00, "w3": 0.90, "w4": 0.60,
                "decay_n": 26, "gate": "news", "gate_p": 0.12, "wins_std": 4,
                "decay": 10, "truncation": 0.08, "neut": "INDUSTRY",
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
        wrap = trial.suggest_categorical("wrap", WRAPS)
        g = trial.suggest_categorical("group", GROUPS)
        sigs = [trial.suggest_categorical(f"sig{i}", SIGS) for i in (1, 2, 3, 4)]
        ws = [trial.suggest_float(f"w{i}", 0.30, 1.80) for i in (1, 2, 3, 4)]
        decay_n = trial.suggest_int("decay_n", 18, 35)
        gate = trial.suggest_categorical("gate", ["news", "none"])
        gate_p = trial.suggest_float("gate_p", 0.05, 0.30)
        wins_std = trial.suggest_int("wins_std", 3, 5)
        decay = trial.suggest_categorical("decay", [8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08])
        neut = trial.suggest_categorical("neut", ["INDUSTRY", "SUBINDUSTRY"])

        settings = dict(FIXED_SETTINGS, universe="TOP3000", decay=decay,
                        truncation=truncation, neutralization=neut)
        expr = build_expression(wrap, g, sigs, ws, decay_n, gate, gate_p, wins_std)
        log.info(f"t{trial.number}: {wrap}/{g} sigs={'+'.join(sigs)} "
                 f"w={'/'.join(f'{w:.2f}' for w in ws)} N={decay_n} gate={gate}>{gate_p:.2f} "
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

        self_corr = None
        if res.ok:
            log.info(f"  SH={res.sharpe:+.3f} FIT={res.fitness:+.3f} TO={res.turnover:.3f} "
                     f"chk={res.checks_passed}/{res.checks_total} alpha={res.alpha_id}")
            # only spend a correlation poll on genuinely strong candidates
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
                    decorrelated = (self_corr is None) or (self_corr < SELF_CORR_MAX)
                    if passed and decorrelated:
                        log.info(f"  *** PASSED + DECORRELATED (corr={self_corr}) — submitting ***")
                        sub = attempt_submit(session, res.alpha_id)
                        rec["submit_response"] = sub
                        if sub.get("ok"):
                            log.info(f"  *** SUBMIT ACCEPTED: {res.alpha_id} ***")
                    elif passed and not decorrelated:
                        log.info(f"  passed IS but self_corr={self_corr} >= {SELF_CORR_MAX} — NOT submitting")
                    else:
                        log.info(f"  fails: {fails[:3]}")
        else:
            log.info(f"  [{res.error[:120]}]")

        append_result(rec)
        if not res.ok: return -10.0
        if res.turnover > 0.50: return res.sharpe - 2.0
        score = res.sharpe + 0.1*res.fitness + (res.checks_passed - 4)*0.5
        if self_corr is not None and self_corr > 0.50:
            score -= 3.0 * (self_corr - 0.50)   # steer TPE toward decorrelated structure
        return score

    try:
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    sys.exit(main())
