"""Mutation search around A1nGR0GW (the v4 champion).

Base expression (Optuna-tuned windows):
    scale(ts_backfill(winsorize(
        multiply(
            subtract(ts_std_dev(high, 39), ts_rank(adv20, 31)),
            ts_std_dev(multiply(cap, open), 18)),
        std=26), 19))

Random generation has plateaued (5 runs, 259 trials, 0 alphas at SH>2.0).
This script bypasses the random generator and submits 20 hand-written
mutations of the champion, each with Optuna over window integers.
"""
from __future__ import annotations
import json, sys, logging
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from mining_pipeline import wq_pipeline as W

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mutate")


# Base "core" between scale(ts_backfill(winsorize(..., std=26), 19))
def wrap(core, outer="scale", winsor=26, backfill=19):
    return f"{outer}(ts_backfill(winsorize({core}, std={winsor}), {backfill}))"


def core(a="high", b="adv20", c="cap", d="open",
         arith_outer="multiply", arith_inner="subtract",
         w1=39, w2=31, w3=18):
    return (f"{arith_outer}("
            f"{arith_inner}(ts_std_dev({a}, {w1}), ts_rank({b}, {w2})), "
            f"ts_std_dev(multiply({c}, {d}), {w3}))")


MUTATIONS = [
    # 0. baseline (sanity check the champion reproduces)
    wrap(core()),

    # field swaps (most stable / lowest-noise PV substitutes)
    wrap(core(a="close")),   # high -> close
    wrap(core(a="vwap")),    # high -> vwap
    wrap(core(d="vwap")),    # open -> vwap

    # outer wrapper swaps (rank/normalize are most different from scale)
    wrap(core(), outer="rank"),
    wrap(core(), outer="normalize"),

    # group_* wrappers (proven to help in v2 best result d5n0rl9Y)
    f"group_rank(ts_backfill(winsorize({core()}, std=26), 19), sector)",
    f"group_zscore(ts_backfill(winsorize({core()}, std=26), 19), industry)",

    # sign flip via subtract reversal (cheap, if signal is inverted this wins)
    wrap("multiply(subtract(ts_rank(adv20, 31), ts_std_dev(high, 39)), "
         "ts_std_dev(multiply(cap, open), 18))"),

    # trade_when entry gate at 0.05 (large move requirement)
    f"trade_when(greater(abs(returns), 0.05), {wrap(core())}, -1)",
]


def main():
    out_path = REPO / "WQ_D0_V6_MUTATE_REPORT.json"

    # auth
    cm_mod = W._load(W.VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"auth ok as {cm.credentials.username}")

    # lock delay=0 since these are D0 mutations
    W.SETTING_SPACE["delay"] = [0]

    n_trials = 3
    base_seed = 731

    all_results = []
    for i, expr in enumerate(MUTATIONS, 1):
        log.info(f"=== [{i}/{len(MUTATIONS)}] mutation: {expr}")
        rs = W.search_one(cm.session, expr, n_trials, base_seed + i)
        all_results.extend(rs)
        with open(out_path, "w") as f:
            json.dump([asdict(r) for r in all_results], f, indent=2)

    surv20 = [r for r in all_results if r.ok and r.sharpe > 2.0
              and r.turnover < 0.25 and r.fitness > 1.3]
    print()
    print("=" * 100)
    print(f"Total: {len(all_results)}, OK: {sum(1 for r in all_results if r.ok)}, "
          f"Submit-eligible (SH>2.0 TO<0.25 FIT>1.3): {len(surv20)}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
