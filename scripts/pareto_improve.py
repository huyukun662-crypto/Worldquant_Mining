"""Batch-5: Pareto improvement over the batch-4 submittable champions.

Incumbents to beat (all from WQ Brain /simulations, delay=1, no IV):
  blLEVxvM  normalize(reverse(ts_av_diff(close,21))) decay=4
            SH 1.32 / TO 0.218 / DD 0.091 / FIT 1.04
  MPpmXdba  normalize(reverse(ts_av_diff(close,21))) decay=6
            SH 1.26 / TO 0.187 / DD 0.086 / FIT 1.04

Objective directions for the Pareto frontier:
    sharpe  ^   fitness ^   turnover v   drawdown v
A candidate Pareto-DOMINATES an incumbent iff it is >= on every objective
and strictly > on at least one.

Variants keep the submittable structure (normalize wrapper + truncation=0.01
to satisfy CONCENTRATED_WEIGHT) and only change the signal core / decay:
  V1 baseline            normalize(reverse(ts_av_diff(close, W)))
  V2 risk-scaled         normalize(divide(reverse(ts_av_diff(close,W)), ts_std_dev(close,W)))
  V3 decay-smoothed      normalize(ts_decay_linear(reverse(ts_av_diff(close,W)), 5))
  V4 winsorized          normalize(winsorize(reverse(ts_av_diff(close,W)), std=4))
  V5 close+vwap blend    normalize(reverse(add(ts_av_diff(close,W), ts_av_diff(vwap,W))))
  V6 risk-scaled+smooth  normalize(ts_decay_linear(divide(reverse(ts_av_diff(close,W)),
                                  ts_std_dev(close,W)), 5))

Run:
    python scripts/pareto_improve.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_d1_pipeline import submit  # noqa: E402

VENDOR = REPO / "vendor" / "worldquant-miner"

# objective name -> +1 if higher-is-better, -1 if lower-is-better
OBJ = {"sharpe": +1, "fitness": +1, "turnover": -1, "drawdown": -1}

INCUMBENTS = [
    {"alpha_id": "blLEVxvM", "decay": 4, "sharpe": 1.32, "turnover": 0.2178,
     "drawdown": 0.0909, "fitness": 1.04,
     "optimized": "normalize(reverse(ts_av_diff(close, 21)))"},
    {"alpha_id": "MPpmXdba", "decay": 6, "sharpe": 1.26, "turnover": 0.1866,
     "drawdown": 0.0855, "fitness": 1.04,
     "optimized": "normalize(reverse(ts_av_diff(close, 21)))"},
]

W = 21
VARIANTS = [
    f"normalize(reverse(ts_av_diff(close, {W})))",
    f"normalize(divide(reverse(ts_av_diff(close, {W})), ts_std_dev(close, {W})))",
    f"normalize(ts_decay_linear(reverse(ts_av_diff(close, {W})), 5))",
    f"normalize(winsorize(reverse(ts_av_diff(close, {W})), std=4))",
    f"normalize(reverse(add(ts_av_diff(close, {W}), ts_av_diff(vwap, {W}))))",
    f"normalize(ts_decay_linear(divide(reverse(ts_av_diff(close, {W})), "
    f"ts_std_dev(close, {W})), 5))",
]
DECAYS = [4, 6]
BASE = {"universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY",
        "truncation": 0.01, "pasteurization": "ON"}


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def dominates(a: dict, b: dict) -> bool:
    """True if a Pareto-dominates b across OBJ (>= all, > at least one)."""
    ge_all, gt_any = True, False
    for k, sign in OBJ.items():
        av, bv = a[k] * sign, b[k] * sign
        if av < bv - 1e-9:
            ge_all = False
        if av > bv + 1e-9:
            gt_any = True
    return ge_all and gt_any


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("auth failed"); return 2
    print(f"authenticated as {cm.credentials.username}")

    combos = [(e, d) for e in VARIANTS for d in DECAYS]
    print(f"running {len(combos)} Pareto-search simulations (delay=1, no IV)")
    results = []
    for i, (expr, decay) in enumerate(combos, 1):
        s = dict(BASE); s["decay"] = decay
        print(f"[{i}/{len(combos)}] decay={decay} :: {expr}")
        res = submit(cm.session, expr, s)
        results.append(res)
        if res.ok:
            print(f"    SH={res.sharpe:+.3f} TO={res.turnover:.3f} DD={res.drawdown:.3f} "
                  f"FIT={res.fitness:+.2f} sub={res.submittable} "
                  f"chk={res.checks_passed}/{res.checks_total} alpha={res.alpha_id}")
        else:
            print(f"    [{res.error[:90]}]")
        with open(REPO / "WQ_MINING_REPORT_batch5.json", "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

    # Build candidate dicts (submittable only) and compare to incumbents.
    cands = [{"alpha_id": r.alpha_id, "decay": r.settings.get("decay"),
              "sharpe": r.sharpe, "turnover": r.turnover, "drawdown": r.drawdown,
              "fitness": r.fitness, "optimized": r.optimized}
             for r in results if r.ok and r.submittable
             and r.sharpe > 1.25 and r.turnover < 0.25]

    print("\n" + "=" * 100)
    print(f"submittable candidates (SH>1.25, TO<0.25): {len(cands)}")
    for inc in INCUMBENTS:
        doms = [c for c in cands if dominates(c, inc)]
        print(f"\nvs incumbent {inc['alpha_id']} (decay={inc['decay']}: "
              f"SH{inc['sharpe']} TO{inc['turnover']} DD{inc['drawdown']} FIT{inc['fitness']}):")
        if not doms:
            print("   (none strictly dominate)")
        for c in doms:
            print(f"   DOMINATES -> SH{c['sharpe']:+.3f} TO{c['turnover']:.3f} "
                  f"DD{c['drawdown']:.3f} FIT{c['fitness']:+.2f} decay={c['decay']} "
                  f"alpha={c['alpha_id']} :: {c['optimized']}")

    # Overall Pareto frontier (incumbents + new candidates)
    pool = cands + INCUMBENTS
    frontier = [x for x in pool if not any(dominates(y, x) for y in pool if y is not x)]
    print("\n--- Pareto frontier (incumbents + new) ---")
    for c in sorted(frontier, key=lambda r: r["sharpe"], reverse=True):
        print(f"   SH{c['sharpe']:+.3f} TO{c['turnover']:.3f} DD{c['drawdown']:.3f} "
              f"FIT{c['fitness']:+.2f} decay={c['decay']} alpha={c.get('alpha_id','-')} "
              f":: {c['optimized']}")
    print("=" * 100)
    json.dump({"candidates": cands, "frontier": frontier},
              open(REPO / "WQ_PARETO_RESULTS.json", "w"), indent=2)
    print("wrote WQ_PARETO_RESULTS.json")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
