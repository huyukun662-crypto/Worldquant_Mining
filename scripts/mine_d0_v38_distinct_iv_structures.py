"""v38 — DISTINCT IV-DERIVED STRUCTURES (decorrelated from skew-LEVEL).

WHY: the IV-skew direction is confirmed strong on D0 — the user already holds
zscore(ts_mean(iv_call_180 - iv_put_180, 20)) at SH 2.36 / FIT 3.26 / TO 0.076
(zero check failures). That means any PLAIN call-put skew LEVEL (any term, any
smoothing) will correlate heavily with the alpha already in the pool. To find a
SECOND submittable D0 alpha we must change the SIGNAL CONSTRUCTION, not just the
smoothing. This miner searches IV-derived structures that are orthogonal to
skew-level by their economics:

  ivhv_gap    : gz(iv_call_T) - gz(hv_T)            variance risk premium
  ivhv_ratio  : gz(iv_call_T / hv_T)                rich/cheap vol
  term_slope  : gz(iv_call_s) - gz(iv_call_l)       call-IV term structure
  skew_slope  : gz(skew_s) - gz(skew_l)             skew TERM STRUCTURE (shape)
  skew_delta  : gz(ts_delta(skew_T, k))             skew MOMENTUM (change vs level)
  skew_norm   : gz(skew_T / (iv_call_T + iv_put_T)) normalized skew

All cross-term subtractions are done AFTER group_zscore so VERIFY can't trip on
mixed vol units. An optional small decorrelated news leg (eps reversal + ls_hint)
can be blended in. EXCLUDES the user's known alpha: no plain skew-level core, no
term-180 plain skew. Measures /correlations/self on every SH>=2.0; SUBMITTABLE
iff SH>=2.0 AND all is.checks pass AND measured corr < 0.70. Does NOT auto-submit.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v38")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V38_RESULTS.json"
SELF_CORR_PENDING_OK = {"SELF_CORRELATION"}
SELF_CORR_MAX = 0.70

FIXED_SETTINGS = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON"
}

GROUPS = ["sector", "industry", "subindustry"]
STRUCTS = ["ivhv_gap", "ivhv_ratio", "term_slope", "skew_slope", "skew_delta", "skew_norm"]
SHORT_TERMS = [10, 20, 30]
LONG_TERMS = [90, 120, 150, 180]
SINGLE_TERMS = [10, 20, 30, 60, 90, 120]   # avoid 180 plain-skew neighbourhood


def _bf(field, bf):
    return f"ts_backfill({field}, {bf})"


def _skew(t):
    return f"(implied_volatility_call_{t} - implied_volatility_put_{t})"


def core_signal(struct, g, t_s, t_l, t_1, delta_k, ivbf):
    """Return the structure core already in group_zscore space (VERIFY-safe)."""
    if struct == "ivhv_gap":
        a = f"group_zscore({_bf(f'implied_volatility_call_{t_1}', ivbf)}, {g})"
        b = f"group_zscore({_bf(f'historical_volatility_{t_1}', ivbf)}, {g})"
        return f"({a} - {b})"
    if struct == "ivhv_ratio":
        r = f"({_bf(f'implied_volatility_call_{t_1}', ivbf)} / {_bf(f'historical_volatility_{t_1}', ivbf)})"
        return f"group_zscore({r}, {g})"
    if struct == "term_slope":
        a = f"group_zscore({_bf(f'implied_volatility_call_{t_s}', ivbf)}, {g})"
        b = f"group_zscore({_bf(f'implied_volatility_call_{t_l}', ivbf)}, {g})"
        return f"({a} - {b})"
    if struct == "skew_slope":
        a = f"group_zscore({_skew(t_s)}, {g})"
        b = f"group_zscore({_skew(t_l)}, {g})"
        return f"({a} - {b})"
    if struct == "skew_delta":
        return f"group_zscore(ts_delta({_skew(t_1)}, {delta_k}), {g})"
    if struct == "skew_norm":
        r = f"({_skew(t_1)} / (implied_volatility_call_{t_1} + implied_volatility_put_{t_1}))"
        return f"group_zscore({r}, {g})"
    raise ValueError(struct)


def eps_ratio(bf):
    return f"({_bf('news_eps_actual', bf)} / {_bf('est_epsr', 250)})"


def build_expression(struct, g, t_s, t_l, t_1, delta_k, ivbf, wA, we, wl, nbf, decay_n, wins_std):
    legs = [f"{wA:.3f} * {core_signal(struct, g, t_s, t_l, t_1, delta_k, ivbf)}"]
    if we > 0.01:
        legs.append(f"{we:.3f} * group_zscore((-1 * {eps_ratio(nbf)}), {g})")
    if wl > 0.01:
        legs.append(f"{wl:.3f} * group_zscore({_bf('news_ls', nbf)}, {g})")
    body = " + ".join(legs)
    inner = f"ts_decay_linear({body}, {decay_n})" if decay_n > 1 else body
    return f"winsorize({inner}, std={wins_std})"


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def append_result(rec):
    if RESULTS_FILE.exists():
        try: data = json.loads(RESULTS_FILE.read_text())
        except: data = []
    else: data = []
    data.append(rec); RESULTS_FILE.write_text(json.dumps(data, indent=2))


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
    ap.add_argument("--trials", type=int, default=180)
    ap.add_argument("--seed", type=int, default=38038)
    args = ap.parse_args()

    cm_mod = _load(VENDOR/"core"/"credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=30)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    base = {"group":"sector","t_s":30,"t_l":180,"t_1":30,"delta_k":20,"ivbf":20,
            "wA":1.0,"we":0.0,"wl":0.0,"nbf":250,"decay_n":4,"wins_std":4,
            "decay":4,"truncation":0.02,"neut":"SUBINDUSTRY","universe":"TOP3000"}
    # one clean seed per structure (truncation/decay/neut mirror the user's strong config)
    study.enqueue_trial({**base, "struct":"ivhv_gap",   "t_1":30})
    study.enqueue_trial({**base, "struct":"ivhv_ratio", "t_1":30})
    study.enqueue_trial({**base, "struct":"skew_slope", "t_s":30, "t_l":180})
    study.enqueue_trial({**base, "struct":"term_slope", "t_s":30, "t_l":180})
    study.enqueue_trial({**base, "struct":"skew_delta", "t_1":30, "delta_k":20})
    study.enqueue_trial({**base, "struct":"skew_norm",  "t_1":30})
    # a couple with a light news decorrelator already mixed in
    study.enqueue_trial({**base, "struct":"ivhv_gap",   "t_1":60, "we":0.30, "wl":0.20})
    study.enqueue_trial({**base, "struct":"skew_slope", "t_s":20, "t_l":150, "we":0.30})

    seen_alphas = set(); seen_exprs = {}
    if RESULTS_FILE.exists():
        try:
            for x in json.loads(RESULTS_FILE.read_text()):
                if x.get("ok") and x.get("alpha_id"): seen_alphas.add(x["alpha_id"])
                s=x.get("settings",{})
                key=(x.get("expression",""), s.get("universe"), s.get("decay"),
                     s.get("truncation"), s.get("neutralization"))
                if x.get("expression"): seen_exprs[str(key)] = x.get("alpha_id","?")
        except: pass
    log.info(f"resume: {len(seen_alphas)} alpha_ids, {len(seen_exprs)} skip-list")

    best = {"score": -99}

    def objective(trial):
        struct = trial.suggest_categorical("struct", STRUCTS)
        g = trial.suggest_categorical("group", GROUPS)
        t_s = trial.suggest_categorical("t_s", SHORT_TERMS)
        t_l = trial.suggest_categorical("t_l", LONG_TERMS)
        t_1 = trial.suggest_categorical("t_1", SINGLE_TERMS)
        delta_k = trial.suggest_categorical("delta_k", [5, 10, 20, 40])
        ivbf = trial.suggest_categorical("ivbf", [5, 20, 60])
        wA = trial.suggest_float("wA", 0.80, 2.50)
        we = trial.suggest_float("we", 0.00, 1.20)
        wl = trial.suggest_float("wl", 0.00, 1.20)
        nbf = trial.suggest_categorical("nbf", [120, 250])
        decay_n = trial.suggest_categorical("decay_n", [1, 4, 12, 20])
        wins_std = trial.suggest_int("wins_std", 3, 5)
        decay = trial.suggest_categorical("decay", [2, 4, 8])
        truncation = trial.suggest_categorical("truncation", [0.02, 0.05, 0.08])
        neut = trial.suggest_categorical("neut", ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET"])
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])

        settings = dict(FIXED_SETTINGS, universe=universe, decay=decay,
                        truncation=truncation, neutralization=neut)
        expr = build_expression(struct, g, t_s, t_l, t_1, delta_k, ivbf,
                                wA, we, wl, nbf, decay_n, wins_std)
        log.info(f"t{trial.number}: {struct}/{g} ts={t_s} tl={t_l} t1={t_1} dk={delta_k} "
                 f"ivbf={ivbf} wA={wA:.2f} we={we:.2f} wl={wl:.2f} N={decay_n} "
                 f"tr={truncation} dec={decay} neut={neut} uni={universe}")
        ekey = str((expr, universe, decay, truncation, neut))
        if ekey in seen_exprs:
            log.info(f"  (skip — already as {seen_exprs[ekey]})")
            return -5.0

        res = wq_submit(session, expr, settings)
        if res.ok and res.alpha_id: seen_exprs[ekey] = res.alpha_id

        rec = {"ts": time.time(), "trial": trial.number, "struct": struct, "params": trial.params,
               "expression": expr, "settings": res.settings, "ok": res.ok,
               "alpha_id": res.alpha_id, "error": res.error,
               "sharpe": res.sharpe, "turnover": res.turnover, "fitness": res.fitness,
               "returns": res.returns, "drawdown": res.drawdown,
               "checks_passed": res.checks_passed, "checks_total": res.checks_total}

        self_corr = None
        if res.ok:
            log.info(f"  SH={res.sharpe:+.3f} FIT={res.fitness:+.3f} TO={res.turnover:.3f} "
                     f"chk={res.checks_passed}/{res.checks_total} alpha={res.alpha_id}")
            if res.sharpe >= 2.00 and res.alpha_id:
                self_corr = self_corr_max(session, res.alpha_id)
                rec["self_corr_max"] = self_corr
                log.info(f"  self_corr_max={self_corr}")
            if res.alpha_id and res.alpha_id not in seen_alphas:
                seen_alphas.add(res.alpha_id)
                ra = session.get(f"https://api.worldquantbrain.com/alphas/{res.alpha_id}", timeout=30)
                if ra.status_code == 200:
                    passed, fails = evaluate_pass(ra.json())
                    rec["all_pass"] = passed; rec["failure_reasons"] = fails
                    submittable = (passed and res.sharpe >= 2.00
                                   and self_corr is not None and self_corr < SELF_CORR_MAX)
                    if submittable:
                        log.info(f"  *** SUBMITTABLE: {struct} SH={res.sharpe:.2f} PASS "
                                 f"DECORRELATED corr={self_corr:.4f} alpha={res.alpha_id} — "
                                 f"surfacing, NOT auto-submitting ***")
                    elif res.sharpe >= 2.00 and self_corr is not None:
                        log.info(f"  SH ok but corr={self_corr:.4f} vs {SELF_CORR_MAX} (pass={passed})")
                    elif not passed:
                        log.info(f"  fails: {fails[:3]}")
        else:
            log.info(f"  [{str(res.error)[:140]}]")

        append_result(rec)
        if not res.ok: return -10.0
        if res.turnover > 0.70: return res.sharpe - 3.0
        score = res.sharpe + 0.05 * res.fitness
        if self_corr is not None:
            if self_corr < SELF_CORR_MAX:
                score += 1.0 + 2.0 * (SELF_CORR_MAX - self_corr)
            else:
                score -= 6.0 * (self_corr - SELF_CORR_MAX + 0.02)
        if score > best["score"]:
            best.update(score=score, sh=res.sharpe, corr=self_corr, alpha=res.alpha_id,
                        struct=struct, expr=expr)
            log.info(f"  >> new best score={score:.3f} ({struct} SH={res.sharpe:.2f} corr={self_corr})")
        return score

    try:
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)
    except KeyboardInterrupt:
        log.info("interrupted"); return 130
    log.info(f"DONE best={best}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
