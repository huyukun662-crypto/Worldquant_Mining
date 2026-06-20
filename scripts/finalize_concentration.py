"""Batch-4: concentration fix for the batch-3 survivor.

Batch-3 surfaced `zscore(reverse(ts_av_diff(close, 21)))` @ decay=4,
SUBINDUSTRY, TOP3000, trunc=0.05 with SH 1.30 / TO 0.216 / DD 0.101 / FIT
1.03 -- it PASSES every IS check except CONCENTRATED_WEIGHT (realised max
single-name weight 0.20 > 0.10 limit). That is a weight-distribution
problem, not a signal problem.

This driver sweeps the concentration levers around that exact survivor:
  * truncation  : 0.01 / 0.02 / 0.03   (tighter alpha truncation lowers the
                  realised max weight)
  * signal cap  : raw zscore vs winsorize(zscore, std=2) vs rank
                  (bounded/uniform weights reduce concentration)
  * decay       : 4 / 6                  (keeps turnover < 0.25)
fixed: delay=1, region USA, SUBINDUSTRY neutralization, TOP3000, no IV fields.

It reuses `mining_pipeline.wq_d1_pipeline.submit` so the metrics/checks
parsing and the submittability gate are identical to the rest of the
pipeline. Writes WQ_MINING_REPORT_batch4.json and prints submittable
survivors.

Run:
    python scripts/finalize_concentration.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_d1_pipeline import submit, FIXED_SETTINGS  # noqa: E402

VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Concentration-controlled variants of the survivor signal (close-price
# mean-reversion via ts_av_diff). winsorize/rank bound the per-name weight.
EXPRESSIONS = [
    "zscore(reverse(ts_av_diff(close, 21)))",                    # baseline
    "winsorize(zscore(reverse(ts_av_diff(close, 21))), std=2)",  # clip outliers
    "rank(reverse(ts_av_diff(close, 21)))",                      # uniform weights
    "normalize(reverse(ts_av_diff(close, 21)))",                 # L1-normalised
]

DECAYS = [4, 6]
TRUNCATIONS = [0.01, 0.02, 0.03]
BASE = {"universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY",
        "pasteurization": "ON"}


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("auth failed"); return 2
    print(f"authenticated as {cm.credentials.username}")

    results = []
    combos = [(e, d, t) for e in EXPRESSIONS for d in DECAYS for t in TRUNCATIONS]
    print(f"running {len(combos)} concentration-fix simulations (delay=1, no IV)")
    for i, (expr, decay, trunc) in enumerate(combos, 1):
        settings = dict(BASE); settings.update(decay=decay, truncation=trunc)
        print(f"[{i}/{len(combos)}] decay={decay} trunc={trunc} :: {expr}")
        res = submit(cm.session, expr, settings)
        results.append(res)
        if res.ok:
            print(f"    SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                  f"DD={res.drawdown:.3f} FIT={res.fitness:+.2f} "
                  f"checks={res.checks_passed}/{res.checks_total} "
                  f"submittable={res.submittable} alpha={res.alpha_id}")
        else:
            print(f"    [{res.error[:90]}]")
        with open(REPO / "WQ_MINING_REPORT_batch4.json", "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

    subs = [r for r in results if r.ok and r.submittable]
    gate = [r for r in results if r.ok and r.sharpe > 1.25 and r.turnover < 0.25]
    print("\n" + "=" * 100)
    print(f"OK: {sum(1 for r in results if r.ok)}/{len(results)}   "
          f"pass SH/TO gate: {len(gate)}   fully submittable: {len(subs)}")
    for r in sorted(subs or gate, key=lambda r: r.sharpe, reverse=True):
        s = r.settings
        print(f"  SH={r.sharpe:+.3f} TO={r.turnover:.3f} DD={r.drawdown:.3f} "
              f"FIT={r.fitness:+.2f} sub={r.submittable} chk={r.checks_passed}/{r.checks_total} "
              f"decay={s['decay']} trunc={s['truncation']} alpha={r.alpha_id}")
        print(f"      {r.optimized}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
