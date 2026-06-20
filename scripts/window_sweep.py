"""Batch-6: window-length sweep to push the Pareto frontier outward.

Batch-5 showed the signal-shape variants do not dominate the champions, but
the lookback WINDOW was never swept (fixed at 21). Shorter windows raise
Sharpe (batch-3: ts_av_diff(close,7) reached SH 1.66) at the cost of
turnover; decay can claw turnover back. This sweeps:

    normalize(reverse(ts_av_diff(close, W)))
    W     in {10, 14, 17, 25, 30}
    decay in {4, 6, 8}
    fixed : USA TOP3000 delay=1 SUBINDUSTRY truncation=0.01 pasteurization=ON

and flags any config that Pareto-DOMINATES the incumbents on
(sharpe ^, fitness ^, turnover v, drawdown v) while remaining submittable.

Run:  python scripts/window_sweep.py
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
from scripts.pareto_improve import dominates, INCUMBENTS, OBJ  # noqa: E402

VENDOR = REPO / "vendor" / "worldquant-miner"

WINDOWS = [10, 14, 17, 25, 30]
DECAYS = [4, 6, 8]
BASE = {"universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY",
        "truncation": 0.01, "pasteurization": "ON"}


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("auth failed"); return 2
    print(f"authenticated as {cm.credentials.username}")

    combos = [(w, d) for w in WINDOWS for d in DECAYS]
    print(f"running {len(combos)} window-sweep simulations (delay=1, no IV)")
    results = []
    for i, (w, decay) in enumerate(combos, 1):
        expr = f"normalize(reverse(ts_av_diff(close, {w})))"
        s = dict(BASE); s["decay"] = decay
        print(f"[{i}/{len(combos)}] W={w} decay={decay}")
        res = submit(cm.session, expr, s)
        results.append(res)
        if res.ok:
            print(f"    SH={res.sharpe:+.3f} TO={res.turnover:.3f} DD={res.drawdown:.3f} "
                  f"FIT={res.fitness:+.2f} sub={res.submittable} "
                  f"chk={res.checks_passed}/{res.checks_total} alpha={res.alpha_id}")
        else:
            print(f"    [{res.error[:90]}]")
        with open(REPO / "WQ_MINING_REPORT_batch6.json", "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

    cands = [{"alpha_id": r.alpha_id, "decay": r.settings.get("decay"),
              "sharpe": r.sharpe, "turnover": r.turnover, "drawdown": r.drawdown,
              "fitness": r.fitness, "optimized": r.optimized}
             for r in results if r.ok and r.submittable
             and r.sharpe > 1.25 and r.turnover < 0.25]

    print("\n" + "=" * 100)
    print(f"submittable candidates: {len(cands)}")
    dominators = []
    for inc in INCUMBENTS:
        doms = [c for c in cands if dominates(c, inc)]
        print(f"\nvs {inc['alpha_id']} (decay={inc['decay']}: SH{inc['sharpe']} "
              f"TO{inc['turnover']} DD{inc['drawdown']} FIT{inc['fitness']}):")
        if not doms:
            print("   (none strictly dominate)")
        for c in doms:
            dominators.append(c)
            print(f"   DOMINATES -> SH{c['sharpe']:+.3f} TO{c['turnover']:.3f} "
                  f"DD{c['drawdown']:.3f} FIT{c['fitness']:+.2f} decay={c['decay']} "
                  f"alpha={c['alpha_id']} :: {c['optimized']}")

    pool = cands + INCUMBENTS
    frontier = [x for x in pool if not any(dominates(y, x) for y in pool if y is not x)]
    print("\n--- Pareto frontier (incumbents + new) ---")
    for c in sorted(frontier, key=lambda r: r["sharpe"], reverse=True):
        print(f"   SH{c['sharpe']:+.3f} TO{c['turnover']:.3f} DD{c['drawdown']:.3f} "
              f"FIT{c['fitness']:+.2f} decay={c['decay']} alpha={c.get('alpha_id','-')} "
              f":: {c['optimized']}")
    print("=" * 100)
    json.dump({"candidates": cands, "dominators": dominators, "frontier": frontier},
              open(REPO / "WQ_WINDOW_SWEEP_RESULTS.json", "w"), indent=2)
    print("wrote WQ_WINDOW_SWEEP_RESULTS.json")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
