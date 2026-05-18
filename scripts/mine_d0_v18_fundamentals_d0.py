"""D0 v17 — Pure fundamentals cross-section (cov=1.00, no trade_when).

Hypothesis: fundamentals are slow-changing, high-coverage, and trade
every stock daily, so:
  - LOW_SUB_UNIVERSE_SHARPE passes naturally (no news-gate concentration)
  - LOW_TURNOVER passes naturally (slow signals)
  - HIGH_TURNOVER passes naturally
  - CONCENTRATED_WEIGHT passes (truncation handles it)
  - The 3 IS checks that gave v11/v12 trouble are no longer the bottleneck

Realistic main-SH ceiling for pure fundamentals is likely ~1.5 (they're
crowded), so this is a long-shot route to chk=7+. But the structural
profile is cleaner than the trade_when family.

Known-working fundamental + PV fields on 2445560398@qq.com:
  - cap, debt_lt, assets (fundamental)
  - close, returns, volume, adv20, vwap, open, high, low (PV)

Signal library composes pair ratios and TS transforms:
  - rank(debt_lt / assets)         leverage
  - rank(adv20 / cap)              turnover/cap
  - rank(ts_zscore(returns, 252))  long-term momentum
  - rank(close / ts_mean(close, 252))  vs 1Y MA
  - rank(ts_delta(cap, 60))        cap momentum
  - rank(-1 * ts_zscore(returns, 20))  short-term mean reversion
  - rank(volume / adv20)           volume surprise
  - rank(close - vwap)             intraday close vs vwap
  - rank(ts_corr(close, volume, 30))  price-volume corr
  - rank(ts_zscore(ts_delta(assets, 60), 60))  asset growth z

TPE picks 1-3 signals, weights, ts_decay_linear N, settings.
Optionally wraps with group_neutralize(., sector/subindustry).
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
log = logging.getLogger("mine-v17")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V18_RESULTS.json"
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
    "delay":          0,        # delay=0 (user requested d0)
    "pasteurization": "ON",
}

# Signal library — known-working fundamental + PV combinations
SIGNALS: dict[str, str] = {
    "lev":             "rank(debt_lt / (assets + 1.0))",
    "turn":            "rank(adv20 / (cap + 1.0))",
    "mom_y":           "rank(ts_zscore(returns, 252))",
    "ma_1y":           "rank(close / ts_mean(close, 252))",
    "ma_60":           "rank(close / ts_mean(close, 60))",
    "cap_mom":         "rank(ts_delta(cap, 60) / (cap + 1.0))",
    "mr_short":        "rank(-1 * ts_zscore(returns, 20))",
    "vol_surprise":    "rank(volume / (adv20 + 1.0))",
    "vwap_dev":        "rank((close - vwap) / (vwap + 1.0))",
    "pv_corr":         "rank(ts_corr(close, volume, 30))",
    "asset_growth_z":  "rank(ts_zscore(ts_delta(assets, 60), 60))",
    "low_vol":         "rank(-1 * ts_std_dev(returns, 60))",
    "skew_60":         "rank(-1 * ts_zscore(returns, 60))",
    "iliq":            "rank(-1 * ts_corr(returns, volume, 60))",
    "ret_skew":        "rank(ts_zscore(returns - ts_mean(returns, 20), 20))",
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


def build_expression(sig1: str, sig2: str | None, sig3: str | None,
                     w1: float, w2: float, w3: float,
                     decay_n: int,
                     neut_wrap: str | None) -> str:
    parts = [f"{w1:.2f} * {SIGNALS[sig1]}"]
    if sig2 and sig2 != sig1:
        parts.append(f"{w2:.2f} * {SIGNALS[sig2]}")
    if sig3 and sig3 not in (sig1, sig2):
        parts.append(f"{w3:.2f} * {SIGNALS[sig3]}")
    body = " + ".join(parts)
    expr = f"ts_decay_linear({body}, {decay_n})"
    if neut_wrap and neut_wrap != "none":
        expr = f"group_neutralize({expr}, {neut_wrap})"
    return expr


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
    ap.add_argument("--trials", type=int, default=80)
    ap.add_argument("--seed", type=int, default=17171)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=14)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed with each single-leg signal (no leg2, no leg3)
    sig_names = list(SIGNALS)
    for s in sig_names:
        idx = sig_names.index(s)
        study.enqueue_trial({
            "sig1_idx": idx, "sig2_idx": -1, "sig3_idx": -1,
            "w1": 1.0, "w2": 0.5, "w3": 0.3,
            "decay_n": 5,
            "neut_wrap": "none",
            "universe": "TOP3000", "decay": 4,
            "truncation": 0.08, "neutralization": "INDUSTRY",
        })

    found = {"alpha_id": None}
    # Avoid re-submitting same expression+settings (WQ returns same alpha_id)
    seen_alphas: set[str] = set()
    seen_exprs: dict[str, str] = {}  # (expr|settings_key) -> prior alpha_id
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
    log.info(f"resume: {len(seen_alphas)} prior alpha_ids, {len(seen_exprs)} prior expr-settings skip-list")

    def objective(trial: optuna.trial.Trial) -> float:
        sig1_idx = trial.suggest_int("sig1_idx", 0, len(sig_names) - 1)
        sig2_idx = trial.suggest_int("sig2_idx", -1, len(sig_names) - 1)
        sig3_idx = trial.suggest_int("sig3_idx", -1, len(sig_names) - 1)
        w1 = trial.suggest_float("w1", 0.5, 2.0)
        w2 = trial.suggest_float("w2", 0.3, 1.5)
        w3 = trial.suggest_float("w3", 0.2, 1.0)
        decay_n = trial.suggest_int("decay_n", 3, 20)
        neut_wrap = trial.suggest_categorical(
            "neut_wrap", ["none", "sector", "subindustry"])
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])
        decay = trial.suggest_categorical("decay", [4, 6, 8, 10, 12])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY", "SECTOR"])

        sig1 = sig_names[sig1_idx]
        sig2 = sig_names[sig2_idx] if sig2_idx >= 0 else None
        sig3 = sig_names[sig3_idx] if sig3_idx >= 0 else None
        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        expr = build_expression(sig1, sig2, sig3, w1, w2, w3,
                                 decay_n, neut_wrap)
        log.info(f"t{trial.number}: s1={sig1} s2={sig2 or '-'} s3={sig3 or '-'} "
                 f"w={w1:.2f}/{w2:.2f}/{w3:.2f} N={decay_n} neut_wrap={neut_wrap} | "
                 f"u={universe} dec={decay} tr={truncation} neut={neutralization[:5]}")
        # Skip if this exact (expr, settings) was already simulated
        expr_key = str((expr, settings.get("universe"), settings.get("delay"),
                         settings.get("decay"), settings.get("truncation"),
                         settings.get("neutralization")))
        if expr_key in seen_exprs:
            log.info(f"  (skip — already simulated as {seen_exprs[expr_key]})")
            return -5.0  # neutral-ish, TPE won't favor
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
            elif res.alpha_id in seen_alphas:
                log.info(f"  (skip duplicate alpha {res.alpha_id})")
        else:
            log.info(f"  [{res.error[:120]}]")

        append_result(rec)

        if not res.ok:
            return -10.0
        if res.turnover > 0.5:
            return res.sharpe - 5.0
        check_bonus = (res.checks_passed - 4) * 0.5
        return res.sharpe + 0.1 * res.fitness + check_bonus

    # Keep mining — each accepted alpha is logged & submitted, the script
    # only exits when the trial budget is exhausted or on Ctrl-C.
    try:
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)
    except KeyboardInterrupt:
        return 130

    print()
    print("=" * 100)
    print(f"DONE — survivors: {found.get('alpha_id')!r} (last one)")
    return 1  # always rc=1 so wrapper restarts (more trials with new TPE seed)


if __name__ == "__main__":
    sys.exit(main())
