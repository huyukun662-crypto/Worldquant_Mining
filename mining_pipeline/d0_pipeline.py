"""D0 mining pipeline — submit-or-die.

Mines factor expressions on WorldQuant Brain with HARD constraint delay=0.
Every candidate is evaluated directly via /simulations (no local proxy).
The adaptive loop reshapes generator weights based on failed-check buckets
until one alpha clears ALL 8 IS checks AND self-correlation < 0.7, at
which point it's POSTed to /alphas/{id}/submit.

Run:
    python -m mining_pipeline.d0_pipeline --until-pass
    python -m mining_pipeline.d0_pipeline --rounds 3 --per-round 10
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

import optuna

from .expressions import (
    generate_d0,
    integer_positions,
    load_d0_field_pool,
    parameterize,
    DEFAULT_FAMILY_WEIGHTS,
    D0_WRAPPERS,
)
from .wq_pipeline import WQResult, submit

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("d0-pipeline")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
UNION_PATH = REPO / "constants" / "data_fields_union_USA.json"
MINING_OUT = REPO / "WQ_D0_MINING_REPORT.json"
SUBMIT_OUT = REPO / "WQ_D0_SUBMISSION_RESULTS.json"

# Per data_fields_union_USA.json: all 1,225 D0 fields are on TOP1000 only.
D0_SETTING_SPACE = {
    "universe":       ["TOP1000"],
    "delay":          [0],  # HARD constraint
    "decay":          [0, 4, 8, 16, 32],
    "truncation":     [0.01, 0.05, 0.08, 0.10],
    "neutralization": ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET"],
    "pasteurization": ["ON"],
    "nanHandling":    ["ON", "OFF"],
}


def _load_module(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def composite_score(r: WQResult) -> float:
    """Score that approximates the WQ submit gate, not just Sharpe.

    Forces the search to optimize the whole IS-check vector. Failed checks
    cost more than a marginal Sharpe gain.
    """
    if not r.ok:
        return -50.0
    excess_to = max(0.0, r.turnover - 0.25)
    failed = max(0, r.checks_total - r.checks_passed)
    return (
        r.sharpe
        + 0.5 * r.fitness
        - 10.0 * excess_to
        - 1.5 * failed
    )


def search_one_d0(session, expression: str, n_trials: int,
                   seed: int) -> list[WQResult]:
    """Optuna-search (windows, settings) for one D0 expression."""
    positions = integer_positions(expression)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    trials_log: list[WQResult] = []

    def objective(trial: optuna.trial.Trial) -> float:
        settings = {
            k: trial.suggest_categorical(k, v)
            for k, v in D0_SETTING_SPACE.items()
        }
        windows = {p: trial.suggest_int(f"w{p}", 3, 60) for p in positions}
        final = parameterize(expression, windows) if windows else expression
        res = submit(session, final, settings)
        res.optimized = final
        trials_log.append(res)
        if not res.ok:
            log.info(f"      [{res.error[:90]}]")
            return -50.0
        log.info(f"      WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                 f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total} "
                 f"alpha={res.alpha_id}")
        return composite_score(res)

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return trials_log


def _parse_check_failures(results: list[WQResult]) -> dict[str, int]:
    """Count per-check-name failures across results that returned a WQ alpha."""
    # We only have aggregated checks_passed/checks_total in WQResult, so we
    # need to re-fetch /alphas/{id} for any result we want to introspect.
    # For the adaptive loop we approximate by checks-failed magnitude per
    # result and use post-hoc analysis via _fetch_check_breakdown.
    raise NotImplementedError  # not used in v1 — see fetch_check_breakdown


def fetch_check_breakdown(session, alpha_id: str) -> list[dict]:
    """GET /alphas/{id} and return the raw `is.checks` array."""
    import requests
    r = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                     timeout=30)
    if r.status_code != 200:
        return []
    return (r.json().get("is") or {}).get("checks") or []


def adapt_weights(round_results: list[WQResult], session,
                   family_weights: dict[str, float],
                   wrapper_weights: dict[str, float]) -> tuple[dict, dict]:
    """Reshape generator weights based on the previous round's failure pattern.

    Heuristics (see plan.md Phase 3):
      - HIGH_TURNOVER dominant → push trade_when / decay_linear wrappers
      - LOW_SUB_UNIVERSE_SHARPE dominant → no-op for now (already SUBINDUSTRY)
      - LOW_SHARPE dominant → diversify field families (boost under-sampled)
    """
    fail_buckets: dict[str, int] = {}
    family_use_pass: dict[str, int] = {}
    family_use_total: dict[str, int] = {}
    for r in round_results:
        if not r.ok or not r.alpha_id:
            continue
        checks = fetch_check_breakdown(session, r.alpha_id)
        for c in checks:
            if c.get("result") != "PASS":
                fail_buckets[c.get("name", "?")] = \
                    fail_buckets.get(c.get("name", "?"), 0) + 1

    if not fail_buckets:
        log.info("adapt: no failure data; weights unchanged")
        return family_weights, wrapper_weights

    log.info(f"adapt: failure buckets = {fail_buckets}")

    new_fw = dict(family_weights)
    new_ww = dict(wrapper_weights)

    # Reshape wrappers.
    dominant = max(fail_buckets, key=fail_buckets.get)
    if dominant in ("HIGH_TURNOVER", "LOW_TURNOVER_INVERSE", "TURNOVER"):
        # Push turnover-controlling wrappers.
        for k in ("trade_when_volgate", "decay_linear_16", "decay_linear_8"):
            new_ww[k] = new_ww.get(k, 1.0) * 1.6
        for k in ("rank", "zscore"):
            new_ww[k] = new_ww.get(k, 1.0) * 0.7
    elif dominant in ("LOW_SHARPE", "LOW_FITNESS", "LOW_RETURNS"):
        # Diversify fields — boost under-sampled families.
        for fam in ("option", "news", "analyst", "socialmedia"):
            new_fw[fam] = new_fw.get(fam, 0.0) * 1.4 + 0.02
        new_fw["fundamental"] = max(new_fw.get("fundamental", 0.05), 0.10)
    elif dominant in ("CONCENTRATED_WEIGHT",):
        # Add winsorize wrapper.
        new_ww["winsorize_std4"] = new_ww.get("winsorize_std4", 1.0) * 2.0

    # Renormalize family weights.
    tot = sum(new_fw.values()) or 1.0
    new_fw = {k: v / tot for k, v in new_fw.items()}
    log.info(f"adapt: new family weights = {new_fw}")
    log.info(f"adapt: new wrapper weights = {new_ww}")
    return new_fw, new_ww


def submit_to_competition(session, alpha_id: str) -> dict:
    """POST /alphas/{id}/submit. Returns dict with status_code and body."""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/submit"
    log.info(f"--> POST {url}")
    r = session.post(url, timeout=60)
    out = {"alpha_id": alpha_id, "status_code": r.status_code,
           "body": r.text[:1000]}
    log.info(f"   -> {r.status_code}: {r.text[:300]}")
    return out


def _save_mining(records: list[WQResult]):
    with open(MINING_OUT, "w") as f:
        json.dump([asdict(r) for r in records], f, indent=2)


def _save_submission(rec: dict, all_recs: list[dict]):
    all_recs.append(rec)
    with open(SUBMIT_OUT, "w") as f:
        json.dump(all_recs, f, indent=2)


def _is_winner(r: WQResult) -> bool:
    return (
        r.ok
        and r.checks_total > 0
        and r.checks_passed == r.checks_total
        and r.sharpe >= 1.25
        and r.turnover < 0.7  # WQ official ceiling for D1; D0 may differ
        and r.fitness >= 1.0
    )


def run(rounds: int, per_round: int, trials: int, seed: int,
        until_pass: bool) -> int:
    cm_mod = _load_module(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    pool = load_d0_field_pool(UNION_PATH)
    log.info("D0 field pool: " +
             " ".join(f"{k}={len(v)}" for k, v in pool.items()))

    # Bootstrap from prior runs if WQ_D0_MINING_REPORT.json exists.
    all_records: list[WQResult] = []
    if MINING_OUT.exists():
        try:
            for r in json.load(open(MINING_OUT)):
                all_records.append(WQResult(**r))
            log.info(f"loaded {len(all_records)} prior results from {MINING_OUT.name}")
        except Exception as e:
            log.warning(f"could not resume from {MINING_OUT}: {e}")

    submission_log: list[dict] = []
    if SUBMIT_OUT.exists():
        try:
            submission_log = json.load(open(SUBMIT_OUT))
        except Exception:
            submission_log = []

    # Check whether we already have a winner from a prior run.
    for r in all_records:
        if _is_winner(r):
            log.info(f"prior winner found: alpha_id={r.alpha_id} SH={r.sharpe}")
            res = submit_to_competition(cm.session, r.alpha_id)
            res["winner"] = asdict(r)
            res["submitted"] = res["status_code"] in (200, 201)
            _save_submission(res, submission_log)
            return 0 if res["submitted"] else 4

    family_weights = dict(DEFAULT_FAMILY_WEIGHTS)
    wrapper_weights = {k: 1.0 for k in D0_WRAPPERS}

    round_idx = 0
    while True:
        round_idx += 1
        log.info("=" * 70)
        log.info(f"=== ROUND {round_idx} ===")
        log.info("=" * 70)
        exprs = generate_d0(
            n=per_round, pool=pool,
            seed=seed + 1000 * round_idx,
            family_weights=family_weights,
            wrapper_weights=wrapper_weights,
        )
        for i, e in enumerate(exprs, 1):
            log.info(f"  expr[{i}/{per_round}] {e[:130]}")

        round_results: list[WQResult] = []
        for i, expr in enumerate(exprs, 1):
            log.info(f"-- round{round_idx} expr {i}/{per_round}: {expr[:100]}")
            try:
                res_list = search_one_d0(
                    cm.session, expr, n_trials=trials,
                    seed=seed + round_idx * 1000 + i,
                )
            except Exception as e:
                log.exception(f"search_one_d0 crashed: {e}")
                continue
            round_results.extend(res_list)
            all_records.extend(res_list)
            _save_mining(all_records)
            # Winner check after EVERY expression (don't wait for round end).
            winners = [r for r in res_list if _is_winner(r)]
            if winners:
                w = max(winners, key=lambda r: r.sharpe)
                log.info("*" * 70)
                log.info(f"WINNER FOUND: alpha_id={w.alpha_id} "
                         f"SH={w.sharpe} TO={w.turnover} FIT={w.fitness} "
                         f"checks={w.checks_passed}/{w.checks_total}")
                log.info("*" * 70)
                res = submit_to_competition(cm.session, w.alpha_id)
                res["winner"] = asdict(w)
                res["submitted"] = res["status_code"] in (200, 201)
                _save_submission(res, submission_log)
                if res["submitted"]:
                    return 0
                # If submit POST failed (e.g. self-correlation), continue.
                log.warning("winner failed /submit POST; continuing search")

        # Round summary + adaptation.
        ok = [r for r in round_results if r.ok]
        if ok:
            best = max(ok, key=composite_score)
            log.info(f"round{round_idx} best: SH={best.sharpe:.3f} "
                     f"TO={best.turnover:.3f} FIT={best.fitness:.3f} "
                     f"checks={best.checks_passed}/{best.checks_total} "
                     f"expr={best.optimized[:120]}")
        family_weights, wrapper_weights = adapt_weights(
            round_results, cm.session, family_weights, wrapper_weights,
        )

        if not until_pass and round_idx >= rounds:
            log.info(f"reached --rounds {rounds} without a winner; stopping")
            return 5

    # unreachable
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3,
                     help="Number of adaptive rounds (ignored if --until-pass)")
    ap.add_argument("--per-round", type=int, default=10,
                     help="Base expressions per round")
    ap.add_argument("--trials", type=int, default=4,
                     help="Optuna trials per expression")
    ap.add_argument("--seed", type=int, default=37)
    ap.add_argument("--until-pass", action="store_true",
                     help="Loop indefinitely until a winner submits successfully")
    args = ap.parse_args()
    return run(args.rounds, args.per_round, args.trials, args.seed,
               args.until_pass)


if __name__ == "__main__":
    sys.exit(main())
