#!/usr/bin/env python3
"""Headless launcher for zhutoutoutousan/worldquant-miner generation_two
with D0 strict patches applied.

Per the cloud-prompt mining process (PROMPT-D0...云端版.md):
- delay=0, sharpe>=2.0, fitness>=1.3
- decay 1-5, truncation 0.005-0.02
- PV-only fields (close/open/high/low/volume/vwap/returns/cap/adv20/sharesout)
- USA region, TOP3000 primary universe

The vendored toolkit at vendor/wq-miner-zhutoutou is GUI-first; this
script wires up the mining components headlessly and dumps results to
D0-mined-alphas-{date}.csv at exit.
"""

from __future__ import annotations

import csv
import datetime
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "wq-miner-zhutoutou"
sys.path.insert(0, str(VENDOR))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("zhutoutou-d0")

# D0 PV-only field whitelist (per cloud prompt).
PV_FIELDS = {"close", "open", "high", "low", "volume", "vwap", "returns",
             "cap", "adv20", "sharesout"}

# D0 hard gates.
SHARPE_FLOOR = 2.0
FITNESS_FLOOR = 1.3
TURNOVER_CEILING = 0.25

CRED_PATH = REPO / "credential.txt"


def load_credentials() -> list[str]:
    """credential.txt is JSON [username, password] or two-line."""
    raw = CRED_PATH.read_text().strip()
    if raw.startswith("["):
        return json.loads(raw)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return lines[:2]


def patch_pv_only(generator):
    """Wrap template_generator.get_data_fields_for_region so it only
    returns PV fields. This kills the fnd6/mdf/anl4/scl12 streams the
    toolkit would otherwise feed to alpha synthesis.
    """
    tg = generator.template_generator
    original = tg.get_data_fields_for_region

    def filtered(region, delay=0, universe=None):
        all_fields = original(region, delay=delay, universe=universe)
        pv = [f for f in all_fields if (f.get("id") if isinstance(f, dict) else f) in PV_FIELDS]
        # If filter wipes everything (cache miss), synthesise placeholders
        if not pv:
            pv = [{"id": name, "type": "MATRIX", "delay": delay,
                   "region": region, "universe": universe or "TOP3000",
                   "category": {"id": "pv", "name": "Price Volume"},
                   "dataset": {"id": "pv1", "name": "Price Volume"},
                   "description": name, "coverage": 1.0,
                   "userCount": 0, "alphaCount": 0,
                   "subcategory": {"id": "pv-base", "name": "PV Base"},
                   "themes": []}
                  for name in sorted(PV_FIELDS)]
        log.info(f"PV filter: returning {len(pv)}/{len(all_fields)} fields for {region} d{delay}")
        return pv
    tg.get_data_fields_for_region = filtered


def write_csv(results: list, out: Path):
    if not results:
        log.warning("no results to dump")
        return
    fields = ["alpha_id", "expression", "region", "universe", "delay",
              "decay", "truncation", "neutralization", "sharpe", "fitness",
              "turnover", "returns", "drawdown", "margin", "status"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            ok = getattr(r, "success", False) and getattr(r, "sharpe", 0) > 0
            sh = getattr(r, "sharpe", 0.0)
            to = getattr(r, "turnover", 0.0)
            fit = getattr(r, "fitness", 0.0)
            if not ok:
                status = "ERROR"
            elif sh >= SHARPE_FLOOR and fit >= FITNESS_FLOOR and to < TURNOVER_CEILING:
                status = "PASSED"
            elif sh < SHARPE_FLOOR:
                status = "FAILED_LOW_SHARPE"
            elif fit < FITNESS_FLOOR:
                status = "FAILED_LOW_FITNESS"
            elif to >= TURNOVER_CEILING:
                status = "FAILED_HIGH_TURNOVER"
            else:
                status = "FAILED_OTHER"
            s = getattr(r, "settings", None)
            w.writerow({
                "alpha_id": getattr(r, "alpha_id", "") or "",
                "expression": getattr(r, "template", ""),
                "region": getattr(s, "region", "") if s else "",
                "universe": getattr(s, "universe", "") if s else "",
                "delay": getattr(s, "delay", 0) if s else 0,
                "decay": getattr(s, "decay", 1) if s else 1,
                "truncation": getattr(s, "truncation", 0.01) if s else 0.01,
                "neutralization": getattr(s, "neutralization", "") if s else "",
                "sharpe": sh, "fitness": fit, "turnover": to,
                "returns": getattr(r, "returns", 0),
                "drawdown": getattr(r, "drawdown", 0),
                "margin": getattr(r, "margin", 0),
                "status": status,
            })
    log.info(f"wrote {out} ({len(results)} rows)")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=200,
                    help="Max simulations to run (default: 200)")
    ap.add_argument("--strategy", choices=["bfs", "dfs"], default="bfs")
    ap.add_argument("--region", default="USA")
    ap.add_argument("--max-runtime-min", type=int, default=180,
                    help="Wall-clock cap (default: 3h)")
    args = ap.parse_args()

    creds = load_credentials()
    log.info(f"loaded credentials for {creds[0]}")

    # Imports must happen AFTER sys.path insert.
    from generation_two.core.enhanced_template_generator_v3 import EnhancedTemplateGeneratorV3
    from generation_two.core.mining.mining_coordinator import MiningCoordinator
    from generation_two.core.mining.search_strategy import SearchStrategy

    log.info("constructing EnhancedTemplateGeneratorV3 ...")
    gen = EnhancedTemplateGeneratorV3(
        credentials=creds,
        db_path=str(REPO / "zhutoutou_d0_backtests.db"),
        ollama_url="http://localhost:11434",   # not running; lazy-loaded only on demand
    )

    patch_pv_only(gen)

    strategy = SearchStrategy.BFS if args.strategy == "bfs" else SearchStrategy.DFS
    coord = MiningCoordinator(
        db_path=str(REPO / "zhutoutou_d0_backtests.db"),
        max_simulations=args.target,
        search_strategy=strategy,
        log_callback=lambda msg: log.info(f"[coord] {msg}"),
    )

    log.info(f"starting mining coordinator (target={args.target}, "
             f"strategy={args.strategy}, region={args.region})")
    coord.start_mining(
        generator=gen,
        simulator_tester=gen.simulator_tester,
        backtest_storage=gen.backtest_storage,
        regions=[args.region],
    )

    deadline = time.time() + args.max_runtime_min * 60
    last_log = 0
    try:
        while time.time() < deadline:
            time.sleep(30)
            stats = coord.stats
            done = stats.get("templates_simulated", 0)
            if done != last_log:
                log.info(f"[{int(time.time()-deadline+args.max_runtime_min*60)/60:.1f}min] "
                         f"simulated={done} success={stats.get('simulations_successful',0)} "
                         f"failed={stats.get('simulations_failed',0)} "
                         f"dupes={stats.get('duplicates_filtered',0)}")
                last_log = done
            if done >= args.target:
                log.info(f"target {args.target} reached"); break
    except KeyboardInterrupt:
        log.info("interrupted; dumping partial results")
    finally:
        coord.stop_mining()
        time.sleep(2)
        results = getattr(gen, "all_results", [])
        today = datetime.date.today().isoformat()
        write_csv(results, REPO / f"D0-mined-all-zhutoutou-{today}.csv")
        passed = [r for r in results
                  if getattr(r, "success", False)
                  and getattr(r, "sharpe", 0) >= SHARPE_FLOOR
                  and getattr(r, "fitness", 0) >= FITNESS_FLOOR
                  and getattr(r, "turnover", 1) < TURNOVER_CEILING]
        write_csv(passed, REPO / f"D0-mined-alphas-zhutoutou-{today}.csv")
        log.info(f"FINAL: {len(results)} total, {len(passed)} PASSED")


if __name__ == "__main__":
    sys.exit(main() or 0)
