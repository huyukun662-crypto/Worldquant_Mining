"""Tune sim settings for two user-supplied fundamental factors.

The user supplied two expressions and asked them to be tuned to pass
submission (SH > 1.25, TO < 0.25):

  F1:  group_rank((40 - ts_arg_max(ts_delay(fn_comp_non_opt_nonvested_number_a,1), 40)) / 40, subindustry)
       user default: subindustry, decay=4, truncation=0.02

  F2:  ts_decay_linear(group_rank(ts_delay(fnd2_a_dfdtxava,1), subindustry), 5)
       user default: industry, decay=0, truncation=0.10

For each factor we Optuna-search the joint setting space:
  decay        in {0, 2, 4, 8, 12, 16, 20, 32}
  truncation   in {0.01, 0.02, 0.05, 0.08, 0.10, 0.15}
  neutralization in {NONE, MARKET, SECTOR, INDUSTRY, SUBINDUSTRY}
  pasteurization in {ON, OFF}
  universe     in {TOP3000, TOP1000, TOP500}

Output: WQ_USER_FACTORS_TUNE.json with all trials + the best
setting per factor.
"""

from __future__ import annotations
import argparse
import importlib.util
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import optuna

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("user-tune")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
    "delay":          1,
}

SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000", "TOP500"],
    "decay":          [0, 2, 4, 8, 12, 16, 20, 32],
    "truncation":     [0.01, 0.02, 0.05, 0.08, 0.10, 0.15],
    "neutralization": ["NONE", "MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"],
    "pasteurization": ["ON", "OFF"],
}

FACTORS = [
    {
        "name": "F1_comp_arg_max",
        "expression": (
            "group_rank((40 - ts_arg_max("
            "ts_delay(fn_comp_non_opt_nonvested_number_a, 1), 40)) / 40, "
            "subindustry)"
        ),
        "user_default": {"universe": "TOP3000", "decay": 4,
                          "truncation": 0.02, "neutralization": "SUBINDUSTRY",
                          "pasteurization": "ON"},
    },
    {
        "name": "F2_dfdtxava_decay",
        "expression": (
            "ts_decay_linear(group_rank("
            "ts_delay(fnd2_a_dfdtxava, 1), subindustry), 5)"
        ),
        "user_default": {"universe": "TOP3000", "decay": 0,
                          "truncation": 0.10, "neutralization": "INDUSTRY",
                          "pasteurization": "ON"},
    },
]

POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 5


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


@dataclass
class TrialResult:
    ok: bool
    factor_name: str
    expression: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    margin: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    self_corr: float | None = None
    alpha_id: str = ""
    error: str = ""
    checks: list = field(default_factory=list)


def submit(session, factor_name: str, expression: str, settings: dict) -> TrialResult:
    full = dict(FIXED_SETTINGS); full.update(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expression}

    for attempt in range(6):
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait); continue
        break
    if r.status_code != 201:
        return TrialResult(ok=False, factor_name=factor_name,
                            expression=expression, settings=full,
                            error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return TrialResult(ok=False, factor_name=factor_name,
                            expression=expression, settings=full,
                            error="no Location header")

    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st == "COMPLETE":
            alpha_id = data.get("alpha", "")
            ra = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                timeout=30)
            if ra.status_code != 200:
                return TrialResult(ok=False, factor_name=factor_name,
                                    expression=expression, settings=full,
                                    alpha_id=alpha_id,
                                    error=f"alpha-get-{ra.status_code}")
            isb = (ra.json().get("is") or {})
            checks = isb.get("checks") or []
            return TrialResult(
                ok=True, factor_name=factor_name, expression=expression,
                settings=full,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                margin=float(isb.get("margin") or 0.0),
                longCount=int(isb.get("longCount") or 0),
                shortCount=int(isb.get("shortCount") or 0),
                checks_passed=sum(1 for c in checks if c.get("result")=="PASS"),
                checks_total=len(checks),
                checks=checks,
                alpha_id=alpha_id,
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return TrialResult(ok=False, factor_name=factor_name,
                                expression=expression, settings=full,
                                error=f"sim-{st}: {data.get('message','')[:300]}")
    return TrialResult(ok=False, factor_name=factor_name,
                        expression=expression, settings=full, error="poll-timeout")


def fetch_self_corr(session, alpha_id: str, timeout_s: int = 90):
    t0 = time.time()
    while True:
        try:
            r = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self",
                timeout=30)
        except Exception as e:
            return None, f"ERROR:{e}"
        if r.status_code in (202, 204) or not r.text.strip():
            if time.time() - t0 > timeout_s: return None, "PENDING"
            time.sleep(5); continue
        if r.status_code == 429:
            time.sleep(15); continue
        if r.status_code != 200:
            return None, f"ERROR:{r.status_code}"
        try:
            data = r.json()
        except Exception:
            if time.time() - t0 > timeout_s: return None, "PENDING"
            time.sleep(5); continue
        v = data.get("max")
        if isinstance(v, (int, float)):
            return float(v), "DONE"
        sprops = (data.get("schema") or {}).get("properties") or []
        col = {p["name"]: i for i, p in enumerate(sprops)
                if isinstance(p, dict) and "name" in p}
        recs = data.get("records") or []
        vals = []
        for row in recs:
            if isinstance(row, list) and "correlation" in col:
                c = row[col["correlation"]]
                if isinstance(c, (int, float)): vals.append(c)
        if vals:
            return float(max(abs(x) for x in vals)), "DONE"
        if time.time() - t0 > timeout_s: return None, "PENDING"
        time.sleep(5)


def search_factor(session, factor: dict, n_trials: int, seed: int):
    """Search the setting space for one factor.  Returns all trial results
    + the best (passes SH > 1.25 AND TO < 0.25 if possible)."""
    expr = factor["expression"]
    name = factor["name"]
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    trials: list[TrialResult] = []

    # Seed with user defaults so we know the baseline.
    log.info(f"--- baseline submission for {name}: {factor['user_default']}")
    baseline = submit(session, name, expr, factor["user_default"])
    trials.append(baseline)
    if baseline.ok:
        log.info(f"    baseline SH={baseline.sharpe:+.3f} TO={baseline.turnover:.3f} "
                  f"FIT={baseline.fitness:+.3f} chk={baseline.checks_passed}/{baseline.checks_total}")
    else:
        log.warning(f"    baseline FAILED: {baseline.error[:120]}")

    def objective(trial):
        settings = {k: trial.suggest_categorical(k, v)
                     for k, v in SETTING_SPACE.items()}
        log.info(f"   trial {trial.number+1}: settings={settings}")
        res = submit(session, name, expr, settings)
        trials.append(res)
        if not res.ok:
            log.info(f"      [{res.error[:80]}]")
            return -10.0
        log.info(f"      SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                  f"FIT={res.fitness:+.3f} chk={res.checks_passed}/{res.checks_total} "
                  f"alpha={res.alpha_id}")
        penalty = 5.0 if res.turnover >= 0.25 else 0.0
        return res.sharpe - penalty

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return trials


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=15,
                     help="Optuna trials per factor (each is 1 WQ simulation)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_USER_FACTORS_TUNE.json"
    all_trials: dict[str, list[TrialResult]] = {}

    for i, factor in enumerate(FACTORS, 1):
        log.info(f"\n=== Factor {i}/{len(FACTORS)}: {factor['name']} ===")
        log.info(f"    expr: {factor['expression']}")
        trials = search_factor(cm.session, factor, args.trials, args.seed + i)
        all_trials[factor["name"]] = trials
        # Save partial after each factor
        with open(out_path, "w") as f:
            json.dump({k: [asdict(t) for t in v] for k, v in all_trials.items()},
                       f, indent=2)
        log.info(f"    ({len(trials)} trials saved)")

    # Pass 2: self-correlation for OK alphas
    log.info("=== pass 2: self-correlation ===")
    for name, trials in all_trials.items():
        for r in trials:
            if not r.ok or not r.alpha_id: continue
            sc, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=60)
            r.self_corr = sc
            log.info(f"   {r.alpha_id} self_corr={sc} ({st})")
    with open(out_path, "w") as f:
        json.dump({k: [asdict(t) for t in v] for k, v in all_trials.items()},
                   f, indent=2)

    # Report
    print()
    print("=" * 130)
    for name, trials in all_trials.items():
        ok = [t for t in trials if t.ok]
        ok.sort(key=lambda t: t.sharpe, reverse=True)
        pass_bar = [t for t in ok if t.sharpe > 1.25 and t.turnover < 0.25]
        print(f"\n### {name} ({len(ok)}/{len(trials)} OK, "
               f"{len(pass_bar)} pass SH>1.25 + TO<0.25):")
        print(f"{'#':<3}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7}  "
               f"{'univ':<8} {'dcy':>3} {'trunc':>6} {'neut':<12} {'pst':<4}  alpha_id")
        for j, t in enumerate(ok[:10], 1):
            s = t.settings
            sc = f"{t.self_corr:+.3f}" if t.self_corr is not None else "  -  "
            print(f"{j:<3}{t.sharpe:7.3f}{t.turnover:7.3f}{t.fitness:7.3f}"
                   f"{t.checks_passed:>3}/{t.checks_total:<2}{sc:>7}  "
                   f"{s.get('universe','?'):<8} {s.get('decay','?'):>3} "
                   f"{s.get('truncation','?'):>6} {s.get('neutralization','?'):<12} "
                   f"{s.get('pasteurization','?'):<4}  {t.alpha_id}")
    print("=" * 130)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
