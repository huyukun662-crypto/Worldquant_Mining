"""Stage 1b: mine STRUCTURALLY DIFFERENT D1 alphas.

The first sweep (`mine_d1.py`) was dominated by price-volume correlation
(`ts_corr(close,volume)`) + vol-normalized reversal. To diversify the
factor pool, this generator draws from distinct structural families that
the first sweep did NOT use:

  A. VWAP positioning      : close vs vwap (over/under-paid)
  B. Intraday range / vol  : (high-low)/close dispersion
  C. Stochastic %K         : position in the rolling high-low channel
  D. Time-since-extreme    : ts_arg_max / ts_arg_min timing
  E. Volume surprise       : volume vs its own rolling mean / ts_rank
  F. Trend slope           : ts_regression of price on a time counter
  G. Liquidity/size tilt   : adv20 / cap composites

All PV (+ slow fundamentals); NO implied-volatility / option fields.
Delay=1. Goes straight to WQ Brain `/simulations`. Reuses the submit /
Result machinery from mine_d1.py.

Usage:
    python scripts/mine_d1_v2.py --n 28 --workers 2 --seed 202
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mine-d1-v2")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

_spec = importlib.util.spec_from_file_location("mine_d1", REPO / "scripts" / "mine_d1.py")
mine_d1 = importlib.util.module_from_spec(_spec); sys.modules["mine_d1"] = mine_d1
_spec.loader.exec_module(mine_d1)
submit = mine_d1.submit

W = (20, 40, 60, 120)          # slow windows -> low turnover
WS = (5, 10, 20)               # secondary windows


def _family(rng: random.Random) -> str:
    fam = rng.choice("ABCDEFG")
    w = rng.choice(W)
    if fam == "A":   # VWAP positioning
        return f"divide(close, vwap)" if rng.random() < .4 else \
               f"ts_mean(divide(close, vwap), {w})"
    if fam == "B":   # intraday range / dispersion
        core = "divide(subtract(high, low), close)"
        return f"ts_mean({core}, {w})" if rng.random() < .6 else f"ts_std_dev({core}, {w})"
    if fam == "C":   # stochastic %K : (close - ts_min(low)) / (ts_max(high)-ts_min(low))
        return (f"divide(subtract(close, ts_min(low, {w})), "
                f"subtract(ts_max(high, {w}), ts_min(low, {w})))")
    if fam == "D":   # time since rolling extreme
        op = rng.choice(("ts_arg_max", "ts_arg_min"))
        f = rng.choice(("close", "high", "low", "volume"))
        return f"{op}({f}, {w})"
    if fam == "E":   # volume surprise
        if rng.random() < .5:
            return f"divide(volume, ts_mean(volume, {w}))"
        return f"ts_rank(volume, {w})"
    if fam == "F":   # trend slope via regression on time counter
        f = rng.choice(("close", "vwap"))
        return f"ts_regression({f}, ts_step({w}), {w}, 0, 2)"
    # G: liquidity / size tilt
    a = rng.choice(("adv20", "cap", "sharesout"))
    return f"ts_mean({a}, {rng.choice(WS)})" if rng.random() < .5 else \
           f"divide({a}, ts_mean({a}, {w}))"


def generate(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    out, seen = [], set()
    guard = 0
    while len(out) < n and guard < n * 60:
        guard += 1
        core = _family(rng)
        if rng.random() < 0.45:      # blend two different families
            other = _family(rng)
            if other != core:
                core = f"{rng.choice(('subtract','add','divide'))}({core}, {other})"
        sign = rng.choice(("", "", "-"))
        wrap = rng.choice(("rank", "zscore", "normalize"))
        sw = rng.choice((5, 10, 20))
        expr = f"{sign}{wrap}(ts_mean(winsorize({core}, std=4), {sw}))"
        if expr in seen:
            continue
        seen.add(expr); out.append(expr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=28)
    ap.add_argument("--seed", type=int, default=202)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--universe", default="TOP3000")
    ap.add_argument("--neutralization", default="SUBINDUSTRY")
    ap.add_argument("--truncation", type=float, default=0.08)
    ap.add_argument("--decay", type=int, default=6)
    ap.add_argument("--max-turnover", type=float, default=0.25)
    ap.add_argument("--out", default="WQ_D1_V2_REPORT.json")
    args = ap.parse_args()

    cm = mine_d1._load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
        base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    exprs = generate(args.n, args.seed)
    log.info(f"generated {len(exprs)} structurally-diverse D1 candidates")
    base = {"universe": args.universe, "neutralization": args.neutralization,
            "truncation": args.truncation, "decay": args.decay}

    results, lock, done = [], threading.Lock(), [0]

    def work(ie):
        idx, e = ie
        time.sleep((idx % args.workers) * 3.0)
        r = submit(cm.session, e, base)
        with lock:
            results.append(r); done[0] += 1
            tag = f"[{done[0]}/{len(exprs)}]"
            if r.ok:
                log.info(f"{tag} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                         f"DD={r.drawdown:.3f} sub={r.submittable} fail={r.failed_checks} :: {e[:55]}")
            else:
                log.info(f"{tag} [{r.error[:60]}] :: {e[:55]}")
            json.dump([asdict(x) for x in results], open(REPO / args.out, "w"), indent=2)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, list(enumerate(exprs))))

    surv = [r for r in results if r.ok and r.submittable and r.sharpe > 1.25
            and r.turnover < args.max_turnover]
    surv.sort(key=lambda r: (r.turnover, abs(r.drawdown), -r.sharpe))
    print("\n" + "=" * 100)
    print(f"OK {sum(1 for r in results if r.ok)}/{len(results)} | "
          f"SUBMITTABLE survivors: {len(surv)}")
    for r in surv:
        print(f"  SH={r.sharpe:.3f} TO={r.turnover:.3f} FIT={r.fitness:.3f} "
              f"DD={r.drawdown:.3f} id={r.alpha_id}  {r.expression[:65]}")
    print("=" * 100)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
