#!/usr/bin/env python3
"""D0 mining + Submit-Alpha orchestrator.

End-to-end:
  1. Authenticate (huyukun662@gmail.com via credential.txt).
  2. Probe whether the account allows delay=0 simulations.
  3. Generate N rare-field × rare-operator expressions.
  4. For each, run a small Optuna sweep over D0 settings via WQ /simulations.
  5. Filter against the full WQ Submit-Alpha gate (sharpe>1.25, TO<0.25,
     fitness>1.0, all is.checks PASS).
  6. POST /alphas/{id}/submit for the best survivor.

Usage:
  python scripts/mine_d0.py --n 40 --trials 6
  python scripts/mine_d0.py --probe-only
  python scripts/mine_d0.py --n 5 --trials 2 --no-submit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

import optuna

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from mining_pipeline import wq_pipeline as wp
from mining_pipeline.d0_expressions import generate as gen_d0

log = logging.getLogger("mine-d0")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# D0 setting space (delay=0 hardcoded; pasteurization ON to clean NaNs).
D0_SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000"],
    "delay":          [0],
    "decay":          [0, 4, 8, 16],
    "truncation":     [0.05, 0.08, 0.10],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR"],
    "pasteurization": ["ON"],
}

FITNESS_FLOOR = 1.0


def probe_d0(session) -> tuple[bool, str]:
    """Submit `rank(close)` at delay=0, TOP3000 — confirms tier access."""
    log.info("probing D0 access with rank(close) ...")
    res = wp.submit(session, "rank(close)", {
        "universe": "TOP3000", "delay": 0, "decay": 0,
        "truncation": 0.08, "neutralization": "INDUSTRY",
        "pasteurization": "ON",
    }, poll_timeout_s=300)
    if res.ok:
        log.info(f"   D0 OK: SH={res.sharpe:+.3f} TO={res.turnover:.3f}")
        return True, ""
    log.error(f"   D0 probe failed: {res.error}")
    return False, res.error


def search_one_d0(session, expr: str, n_trials: int, seed: int):
    """Optuna over D0 settings only (no expression-window mutation —
    rare fields rarely need lookback tuning, and we want to minimise
    cost)."""
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    trials_log: list[wp.WQResult] = []

    def objective(trial):
        settings = {k: trial.suggest_categorical(k, v)
                    for k, v in D0_SETTING_SPACE.items()}
        log.info(f"   trial: {settings}")
        res = wp.submit(session, expr, settings)
        trials_log.append(res)
        if not res.ok:
            log.info(f"      [{res.error[:120]}]")
            return -10.0
        score = res.sharpe - (5.0 if res.turnover >= wp.TURNOVER_CEILING else 0.0)
        log.info(f"      WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                 f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total}")
        return score

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return trials_log


def submit_alpha(session, alpha_id: str, poll_s: int = 300) -> dict:
    """POST /alphas/{id}/submit and poll until terminal.

    Pattern from vendor/worldquant-miner/auto_evolution.py:94.
    """
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/submit"
    log.info(f"submitting alpha {alpha_id} ...")
    r = session.post(url, timeout=30)
    if r.status_code not in (200, 201):
        return {"ok": False, "error": f"submit-{r.status_code}: {r.text[:300]}"}
    progress_url = r.headers.get("Location") or url
    t0 = time.time()
    last = None
    while time.time() - t0 < poll_s:
        time.sleep(5)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code not in (200, 201):
            continue
        try:
            data = rp.json()
        except Exception:
            continue
        last = data
        st = data.get("status", "")
        log.info(f"   submit status: {st}")
        if st in ("COMPLETE", "PENDING", "SUBMITTED"):
            return {"ok": True, "status": st, "data": data}
        if st in ("ERROR", "FAILED"):
            return {"ok": False, "error": f"submit-{st}: {data.get('message','')[:300]}",
                    "data": data}
    return {"ok": True, "status": "TIMEOUT-OK",
            "note": "polled out; check WQ UI", "data": last}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40,
                    help="Number of rare-D0 expressions to generate")
    ap.add_argument("--trials", type=int, default=6,
                    help="Optuna trials per expression")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", type=str, default="WQ_D0_MINING_REPORT.json")
    ap.add_argument("--submit-out", type=str, default="WQ_D0_SUBMISSION_RESULT.json")
    ap.add_argument("--probe-only", action="store_true")
    ap.add_argument("--no-submit", action="store_true",
                    help="Skip the /alphas/{id}/submit step (mine only)")
    args = ap.parse_args()

    cm_mod = wp._load(wp.VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    ok, err = probe_d0(cm.session)
    if not ok:
        log.error(f"D0 not available on this account: {err}")
        return 3
    if args.probe_only:
        return 0

    exprs = gen_d0(args.n, seed=args.seed)
    log.info(f"generated {len(exprs)} D0 rare-field × rare-op expressions")
    for e in exprs[:10]:
        log.info(f"   {e}")

    all_results: list[wp.WQResult] = []
    for i, e in enumerate(exprs, 1):
        log.info(f"=== [{i}/{len(exprs)}] {e}")
        try:
            trials = search_one_d0(cm.session, e, args.trials, args.seed + i)
        except Exception as ex:
            log.error(f"   trial loop crashed: {ex}")
            continue
        all_results.extend(trials)
        with open(args.out, "w") as f:
            json.dump([asdict(r) for r in all_results], f, indent=2)

    # Full WQ Submit-Alpha gate
    survivors = [r for r in all_results
                 if r.ok
                 and r.sharpe > wp.SHARPE_FLOOR
                 and r.turnover < wp.TURNOVER_CEILING
                 and r.fitness > FITNESS_FLOOR
                 and r.checks_total > 0
                 and r.checks_passed == r.checks_total]
    survivors.sort(key=lambda r: r.fitness, reverse=True)

    print("=" * 110)
    print(f"trials run: {len(all_results)}  ok: {sum(1 for r in all_results if r.ok)}  "
          f"survivors (passes ALL submit checks): {len(survivors)}")
    for r in survivors[:10]:
        print(f"  FIT={r.fitness:+.3f} SH={r.sharpe:+.3f} TO={r.turnover:.3f} "
              f"{r.checks_passed}/{r.checks_total}  {r.alpha_id}  {r.expression[:80]}")
    print("=" * 110)

    if not survivors:
        log.warning("no survivor passes the full submit gate; nothing to submit")
        return 0
    if args.no_submit:
        log.info("--no-submit: stopping before /alphas/{id}/submit")
        return 0

    best = survivors[0]
    log.info(f"best alpha: {best.alpha_id}  fitness={best.fitness:+.3f}  "
             f"expr={best.expression}")
    result = submit_alpha(cm.session, best.alpha_id)
    out = {
        "alpha_id": best.alpha_id,
        "expression": best.expression,
        "settings": best.settings,
        "is_metrics": {
            "sharpe": best.sharpe, "turnover": best.turnover,
            "fitness": best.fitness, "returns": best.returns,
            "drawdown": best.drawdown,
            "checks_passed": best.checks_passed,
            "checks_total": best.checks_total,
        },
        "submit": result,
    }
    with open(args.submit_out, "w") as f:
        json.dump(out, f, indent=2)
    log.info(f"wrote {args.submit_out}")
    print(json.dumps(out, indent=2))
    return 0 if result.get("ok") else 4


if __name__ == "__main__":
    sys.exit(main() or 0)
