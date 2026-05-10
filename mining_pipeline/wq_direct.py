"""WQ-direct miner: skip the (miscalibrated) local triage entirely.

Rationale
---------
After WQ_MINING_REPORT.json (commit a02a295) we have hard evidence that
local-251-ticker yfinance Sharpe DOES NOT generalize: 4 candidates that
beat the local SH>1.25 / OS>=IS gate land at WQ_SH 0.0-0.5 across every
neutralization / universe / decay combination. Per CLAUDE.md the local
backtest is a "fast triage proxy" -- but its precision is so poor it
mostly surfaces volume-volatility patterns that get neutralized away
on TOP3000-INDUSTRY.

This script throws out the local triage and uses WQ Brain itself as
the evaluator from the start:

    1. Generate N structurally-diverse random expressions
       (operators x PV fields, no template reuse).
    2. Submit each to WQ Brain `/simulations` with a fixed sane
       settings template (TOP3000, INDUSTRY, decay=4, trunc=0.08,
       pasteurization=ON, maxTrade=OFF, maxPosition=OFF) -- exactly
       the user's canonical config from the screenshot.
    3. Persist every result to disk after each submission so a crash
       mid-run preserves work.
    4. After all submissions, gate on WQ-canonical thresholds
       (WQ_SH > 1.25, TO < 0.25) and greedy-pick K factors with
       *distinct skeletons* in WQ_SH-descending order.

Throughput
----------
~100 s per WQ submission. N=60 candidates ~= 1.7 hours. Plan the
candidate budget accordingly.

Run:
    python -m mining_pipeline.wq_direct --n 60 --k 4
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .expressions import generate
from .extract_uncorrelated import skeleton
from .wq_pipeline import FIXED_SETTINGS, submit, WQResult

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wq-direct")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# The "default canonical settings" from the user's screenshot. We keep
# these constant for the screening pass so that WQ_SH differences
# attribute to expression structure, not to setting tuning. Setting
# tuning happens in a second pass (wq_pipeline.py with
# --from-report --freeze-windows) only on the survivors of this stage.
SCREEN_SETTINGS = {
    "universe":       "TOP3000",
    "delay":          1,
    "decay":          4,
    "truncation":     0.08,
    "neutralization": "INDUSTRY",
    "pasteurization": "ON",
}

WQ_SHARPE_FLOOR = 1.25
WQ_TURNOVER_CEILING = 0.25


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _save(out_path: Path, results: list[WQResult], config: dict) -> None:
    payload = {
        "config": config,
        "stats": {
            "submitted": len(results),
            "ok": sum(1 for r in results if r.ok),
            "above_floor": sum(1 for r in results
                                if r.ok and r.sharpe > WQ_SHARPE_FLOOR
                                and r.turnover < WQ_TURNOVER_CEILING),
        },
        "results": [asdict(r) for r in results],
    }
    out_path.write_text(json.dumps(payload, indent=2))


def greedy_distinct_skeleton(results: list[WQResult], k: int) -> list[WQResult]:
    """Greedy: pick top-k WQ_SH survivors with distinct skeleton fingerprints."""
    survivors = [r for r in results
                  if r.ok and r.sharpe > WQ_SHARPE_FLOOR
                  and r.turnover < WQ_TURNOVER_CEILING]
    survivors.sort(key=lambda r: r.sharpe, reverse=True)
    picked: list[WQResult] = []
    used = set()
    for r in survivors:
        if len(picked) >= k:
            break
        try:
            sk = skeleton(r.expression)
        except Exception:
            continue
        if sk in used:
            continue
        used.add(sk)
        picked.append(r)
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60,
                     help="Number of candidate expressions to submit")
    ap.add_argument("--k", type=int, default=4,
                     help="Target number of distinct-skeleton survivors")
    ap.add_argument("--seed", type=int, default=137)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--out", type=str, default="WQ_DIRECT_REPORT.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    # The sandbox env regenerates TLS certs with NotBefore = current
    # second, so the first auth call occasionally races the cert. Retry.
    auth_ok = False
    for attempt in range(6):
        if cm.authenticate(auto_load=True, auto_prompt=False):
            auth_ok = True
            break
        log.warning(f"auth attempt {attempt+1} failed; sleeping {2 * (attempt+1)}s")
        time.sleep(2 * (attempt + 1))
    if not auth_ok:
        log.error("authentication failed after retries")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")

    log.info(f"generating {args.n} expressions (seed={args.seed}, "
             f"max_depth={args.max_depth}); dedup by skeleton")
    raw = generate(args.n * 2, seed=args.seed, max_depth=args.max_depth)
    seen_sk: set[str] = set()
    candidates: list[str] = []
    for e in raw:
        try:
            sk = skeleton(e)
        except Exception:
            continue
        if sk in seen_sk:
            continue
        seen_sk.add(sk)
        candidates.append(e)
        if len(candidates) >= args.n:
            break
    log.info(f"  -> {len(candidates)} unique-skeleton candidates")

    log.info(f"will submit {len(candidates)} simulations to WQ Brain "
             f"(~{len(candidates) * 100 / 60:.0f} min at ~100s/sim) "
             f"using fixed screen settings: {SCREEN_SETTINGS}")

    config = {
        "n_requested": args.n, "k": args.k, "seed": args.seed,
        "max_depth": args.max_depth,
        "screen_settings": SCREEN_SETTINGS,
        "wq_sharpe_floor": WQ_SHARPE_FLOOR,
        "wq_turnover_ceiling": WQ_TURNOVER_CEILING,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    out_path = Path(args.out)

    results: list[WQResult] = []
    t0 = time.time()
    for i, expr in enumerate(candidates, 1):
        log.info(f"[{i}/{len(candidates)}] expr: {expr[:100]}")
        res = submit(cm.session, expr, SCREEN_SETTINGS)
        results.append(res)
        if res.ok:
            log.info(f"   WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                     f"FIT={res.fitness:+.3f} ckh={res.checks_passed}/{res.checks_total}")
        else:
            log.info(f"   [{res.error[:120]}]")
        _save(out_path, results, config)

    elapsed = time.time() - t0
    config["elapsed_seconds"] = round(elapsed, 1)
    _save(out_path, results, config)
    log.info(f"submission done in {elapsed/60:.1f} min")

    picked = greedy_distinct_skeleton(results, args.k)
    log.info(f"distinct-skeleton survivors above WQ thresholds: {len(picked)}")

    print()
    print("=" * 110)
    print(f"Submitted: {len(results)}   OK: {sum(1 for r in results if r.ok)}   "
          f"Above floor: {sum(1 for r in results if r.ok and r.sharpe > WQ_SHARPE_FLOOR and r.turnover < WQ_TURNOVER_CEILING)}")
    print(f"Picked (distinct skeleton, top-{args.k} by WQ_SH): {len(picked)}")
    print()
    if picked:
        print(f"{'WQ_SH':>7}{'TO':>7}{'FIT':>7}  alpha_id  expression")
        for r in picked:
            print(f"{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}  "
                  f"{r.alpha_id:<10} {r.expression[:80]}")
    print("=" * 110)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
