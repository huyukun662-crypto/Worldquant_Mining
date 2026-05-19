"""D0 v23 — Expanded operator + Alpha101 templates, pure PV only.

User context: 22 prior versions all capped at SH 1.66 chk=6/8 (only
LOW_SHARPE fails). Explore agent identified that only 11 of ~180
catalogued WQ operators were ever used. Alpha101 templates that
historically achieved SH > 2 use three structures absent from v11-v22:
  - Stacked decay-rank composites (max/min of two ranked decay branches)
  - Argmax/argmin timing (when extreme occurred, orthogonal to z-scores)
  - Non-linear cross-terms (signed_power on rank products)

v23 deploys 33 pure-PV templates across these three pools and TPE-tunes
their integer windows + simulation settings. Pure PV only per user
constraint ("纯量价不要混合"); no option/sentiment/news/fundamentals.

Each template is a function (n1, n2, n3) -> FASTEXPR string. TPE picks
template_idx and three integer windows. Outer wraps add an optional
final transform (winsorize / scale / group_neut).

Honest expectation: ~25-30% probability of breaking SH 2.0.
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
log = logging.getLogger("mine-v23")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

RESULTS_FILE = REPO / "WQ_D0_V23_RESULTS.json"
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


# Template library. Each entry is (label, builder_fn) where
# builder_fn(n1, n2, n3) -> FASTEXPR string. n1/n2/n3 are TPE-tunable.
# Pool A: Alpha101 winners (pure-PV subset).
# Pool B: stacked decay-rank composites (max-of-two-rank-branches structure).
# Pool C: hand-crafted using operators v11-v22 never touched
#         (ts_skewness/kurtosis, ts_arg_max/min, winsorize, scale,
#          signed_power, vector_neutralize, group_rank).


def _a001(n1, n2, n3):
    # alpha001: timing of vol-conditional extreme
    return (f"rank(ts_arg_max(signed_power(if_else(returns < 0, "
            f"ts_std_dev(returns, {n1}), close), 2), {n2})) - 0.5")


def _a006(n1, n2, n3):
    return f"-1 * ts_corr(open, volume, {n1})"


def _a012(n1, n2, n3):
    return f"sign(ts_delta(volume, 1)) * (-1 * ts_delta(close, {n1}))"


def _a014(n1, n2, n3):
    return f"(-1 * rank(ts_delta(returns, {n1}))) * ts_corr(open, volume, {n2})"


def _a019(n1, n2, n3):
    return (f"(-1 * sign((close - ts_delay(close, {n1})) + ts_delta(close, {n1}))) "
            f"* (1 + rank(1 + ts_sum(returns, {n2})))")


def _a023(n1, n2, n3):
    return (f"if_else(ts_mean(high, {n1}) < high, -1 * ts_delta(high, {n2}), 0)")


def _a032(n1, n2, n3):
    return (f"scale(ts_mean(close, {n1}) - close) "
            f"+ {n2} * scale(ts_corr(vwap, ts_delay(close, 5), {n3}))")


def _a040(n1, n2, n3):
    return f"(-1 * rank(ts_std_dev(high, {n1}))) * ts_corr(high, volume, {n2})"


def _a041(n1, n2, n3):
    # midprice deviation; n's unused (kept for uniform signature)
    return f"(power(high * low, 0.5) - vwap)"


def _a042(n1, n2, n3):
    return f"rank((vwap - close)) / rank((vwap + close))"


def _a046(n1, n2, n3):
    return (f"if_else((ts_delay(close, {n1}) - ts_delay(close, {n2})) / {n1} "
            f"- (ts_delay(close, 0) - ts_delay(close, {n1})) / {n1} > 0.25, "
            f"-1, 1) * (close - ts_delay(close, 1))")


def _a052(n1, n2, n3):
    return (f"(-1 * ts_min(low, {n1}) + ts_delay(ts_min(low, {n1}), {n2})) "
            f"* rank((ts_sum(returns, {n3}) - ts_sum(returns, {n1})) / {n3}) "
            f"* ts_rank(volume, {n1})")


def _a053(n1, n2, n3):
    return (f"-1 * ts_delta((((close - low) - (high - close)) "
            f"/ (close - low + 0.001)), {n1})")


def _a054(n1, n2, n3):
    return f"(-1 * (low - close) * power(open, 5)) / ((low - high + 0.001) * power(close, 5))"


def _a057(n1, n2, n3):
    return (f"0 - ((close - vwap) / ts_decay_linear(rank(ts_arg_max(close, {n1})), {n2}))")


def _a060(n1, n2, n3):
    return (f"(2 * scale(rank(((close - low) - (high - close)) / (high - low + 0.001) * volume))) "
            f"- scale(rank(ts_arg_max(close, {n1})))")


def _a101(n1, n2, n3):
    return f"(close - open) / (high - low + 0.001)"


# Pool B — stacked decay-rank composites
def _b071(n1, n2, n3):
    # max(ts_rank(ts_decay_linear(ts_corr(ts_rank(close,5), ts_rank(adv20,5), 10), 8), 16),
    #     ts_rank(ts_decay_linear(rank(((low+open) - 2*vwap))^2, 8), 16))
    return (f"max(ts_rank(ts_decay_linear(ts_corr(ts_rank(close, {n1}), "
            f"ts_rank(adv20, {n1}), {n2}), {n2}), {n3}), "
            f"ts_rank(ts_decay_linear(power(rank((low + open) - 2 * vwap), 2), "
            f"{n2}), {n3}))")


def _b073(n1, n2, n3):
    return (f"max(rank(ts_decay_linear(ts_delta(vwap, {n1}), {n2})), "
            f"ts_rank(ts_decay_linear(((ts_delta((0.5 * close + 0.5 * open), 2) "
            f"/ (0.5 * close + 0.5 * open + 0.001)) * -1), {n3}), {n3})) * -1")


def _b077(n1, n2, n3):
    return (f"min(rank(ts_decay_linear(((high + low) / 2 + high - (vwap + high)), {n1})), "
            f"rank(ts_decay_linear(ts_corr((high + low) / 2, adv20, {n2}), {n3})))")


def _b088(n1, n2, n3):
    return (f"min(rank(ts_decay_linear(((rank(open) + rank(low)) - (rank(high) + rank(close))), {n1})), "
            f"ts_rank(ts_decay_linear(ts_corr(ts_rank(close, {n2}), ts_rank(adv20, {n2}), {n2}), {n3}), {n3}))")


def _b092(n1, n2, n3):
    return (f"min(ts_rank(ts_decay_linear(if_else(((high + low) / 2 + close) < (low + open), 1, 0), {n1}), {n2}), "
            f"ts_rank(ts_decay_linear(ts_corr(rank(low), rank(adv20), {n2}), {n3}), {n3}))")


def _b094(n1, n2, n3):
    return (f"-1 * (rank((vwap - ts_min(vwap, {n1}))) "
            f"* ts_rank(ts_corr(ts_rank(vwap, {n2}), ts_rank(adv20, {n2}), {n3}), {n3}))")


def _b096(n1, n2, n3):
    return (f"-1 * max(ts_rank(ts_decay_linear(ts_corr(rank(vwap), rank(volume), {n1}), {n2}), {n2}), "
            f"ts_rank(ts_decay_linear(ts_arg_max(ts_corr(ts_rank(close, {n2}), "
            f"ts_rank(adv20, {n2}), {n3}), {n3}), {n2}), {n2}))")


def _b101_like(n1, n2, n3):
    # custom 2-branch composite: rank of decayed mom vs rank of decayed reversion
    return (f"max(ts_rank(ts_decay_linear(rank(ts_zscore(returns, {n1})), {n2}), {n3}), "
            f"ts_rank(ts_decay_linear(rank(-1 * ts_zscore(returns, {n2})), {n2}), {n3}))")


# Pool C — hand-crafted with untried operators
def _c_skew(n1, n2, n3):
    return f"-1 * rank(ts_skewness(returns, {n1}))"


def _c_argmax_dist(n1, n2, n3):
    return f"rank(({n1} - ts_arg_max(close, {n1})) / {n1})"


def _c_argmin_dist(n1, n2, n3):
    return f"rank(({n1} - ts_arg_min(close, {n1})) / {n1})"


def _c_kurt_signed(n1, n2, n3):
    return f"-1 * sign(ts_skewness(returns, 60)) * rank(ts_kurtosis(returns, {n1}))"


def _c_range_pos(n1, n2, n3):
    return (f"scale(winsorize((close - ts_min(low, {n1})) "
            f"/ (ts_max(high, {n1}) - ts_min(low, {n1}) + 0.001), std=4))")


def _c_vol_arg(n1, n2, n3):
    return f"rank(ts_arg_max(ts_std_dev(returns, {n1}), {n2}))"


def _c_corr_skew(n1, n2, n3):
    return f"rank(ts_corr(rank(returns), ts_skewness(returns, {n1}), {n2}))"


def _c_decay_sp(n1, n2, n3):
    return f"ts_decay_linear(signed_power(ts_zscore(returns, {n1}), 0.5), {n2})"


def _c_group_mom_resid(n1, n2, n3):
    return (f"group_rank(returns, subindustry) - "
            f"group_rank(ts_delay(returns, {n1}), subindustry)")


def _c_vector_neut_mom(n1, n2, n3):
    return f"vector_neut(ts_zscore(returns, {n1}), ts_std_dev(returns, 60))"


TEMPLATES = [
    # Pool A — Alpha101 winners
    ("a001",      _a001),
    ("a006",      _a006),
    ("a012",      _a012),
    ("a014",      _a014),
    ("a019",      _a019),
    ("a023",      _a023),
    ("a032",      _a032),
    ("a040",      _a040),
    ("a041",      _a041),
    ("a042",      _a042),
    ("a046",      _a046),
    ("a052",      _a052),
    ("a053",      _a053),
    ("a054",      _a054),
    ("a057",      _a057),
    ("a060",      _a060),
    ("a101",      _a101),
    # Pool B — stacked decay-rank
    ("b071",      _b071),
    ("b073",      _b073),
    ("b077",      _b077),
    ("b088",      _b088),
    ("b092",      _b092),
    ("b094",      _b094),
    ("b096",      _b096),
    ("b101_like", _b101_like),
    # Pool C — untried operators
    ("c_skew",         _c_skew),
    ("c_argmax_dist",  _c_argmax_dist),
    ("c_argmin_dist",  _c_argmin_dist),
    ("c_kurt_signed",  _c_kurt_signed),
    ("c_range_pos",    _c_range_pos),
    ("c_vol_arg",      _c_vol_arg),
    ("c_corr_skew",    _c_corr_skew),
    ("c_decay_sp",     _c_decay_sp),
    ("c_group_mom_resid", _c_group_mom_resid),
    ("c_vector_neut_mom", _c_vector_neut_mom),
]


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


def build_expression(tpl_idx: int, n1: int, n2: int, n3: int,
                     outer_wrap: str) -> str:
    label, fn = TEMPLATES[tpl_idx]
    inner = fn(n1, n2, n3)
    if outer_wrap == "winsorize_4":
        inner = f"winsorize({inner}, std=4)"
    elif outer_wrap == "scale":
        inner = f"scale({inner})"
    elif outer_wrap == "group_neut_subindustry":
        inner = f"group_neutralize({inner}, subindustry)"
    elif outer_wrap == "rank_outer":
        inner = f"rank({inner})"
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
    ap.add_argument("--trials", type=int, default=150)
    ap.add_argument("--seed", type=int, default=23232)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session = cm.session

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.seed, n_startup_trials=30)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Seed every template with baseline windows (n1=10, n2=20, n3=5)
    for idx, (label, _) in enumerate(TEMPLATES):
        study.enqueue_trial({
            "tpl_idx": idx,
            "n1": 10, "n2": 20, "n3": 5,
            "outer_wrap": "none",
            "decay": 4, "truncation": 0.08,
            "neutralization": "INDUSTRY",
            "universe": "TOP3000",
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
        tpl_idx = trial.suggest_int("tpl_idx", 0, len(TEMPLATES) - 1)
        n1 = trial.suggest_int("n1", 3, 30)
        n2 = trial.suggest_int("n2", 5, 60)
        n3 = trial.suggest_int("n3", 8, 120)
        outer_wrap = trial.suggest_categorical(
            "outer_wrap",
            ["none", "winsorize_4", "scale", "group_neut_subindustry", "rank_outer"])
        decay = trial.suggest_categorical("decay", [4, 6, 8, 12, 16, 20])
        truncation = trial.suggest_categorical("truncation", [0.05, 0.08, 0.10])
        neutralization = trial.suggest_categorical(
            "neutralization", ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "FAST"])
        universe = trial.suggest_categorical("universe", ["TOP3000", "TOP1000"])

        settings = dict(FIXED_SETTINGS)
        settings.update(universe=universe, decay=decay,
                        truncation=truncation, neutralization=neutralization)

        label = TEMPLATES[tpl_idx][0]
        expr = build_expression(tpl_idx, n1, n2, n3, outer_wrap)
        log.info(f"t{trial.number}: tpl={label} n={n1}/{n2}/{n3} wrap={outer_wrap} | "
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
            "ts": time.time(), "trial": trial.number, "tpl": label,
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
