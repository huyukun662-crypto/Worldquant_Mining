"""Hyperparam sweep on the absolute champion (blNxvooZ) to maximize SH.

blNxvooZ = champion + vwap-close, SH 2.70 FIT 1.90 at default (TOP3000,
INDUSTRY, decay=8, trunc=0.05). This module sweeps decay × truncation ×
universe × neutralization to see if there's a better corner of setting
space.

Run:
    python -m mining_pipeline.champion_optimize
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("champ-opt")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, SimResult, _load, VENDOR
)

# Reigning best alpha expression - the SH=2.70 blNxvooZ
CHAMPION_EXPR = (
    "rank((rank((rank((rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_chg12msip, 120), 20)))"
    " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_fangma_rvm_usa_fangma_rvm6, 120), 20))))))) "
    "+ (-1 * (rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60))))))) "
    "+ (rank(divide(subtract(vwap, close), close))))"
)


# Smart sweep: pick 8 high-priority settings rather than full grid
SETTINGS_GRID = [
    # decay variants
    {"decay": 4,  "truncation": 0.05, "neutralization": "INDUSTRY",   "universe": "TOP3000"},
    {"decay": 16, "truncation": 0.05, "neutralization": "INDUSTRY",   "universe": "TOP3000"},
    {"decay": 32, "truncation": 0.05, "neutralization": "INDUSTRY",   "universe": "TOP3000"},
    # tighter truncation
    {"decay": 8,  "truncation": 0.01, "neutralization": "INDUSTRY",   "universe": "TOP3000"},
    {"decay": 8,  "truncation": 0.02, "neutralization": "INDUSTRY",   "universe": "TOP3000"},
    # neutralization variants (we know SECTOR/SUBI/MARKET work on lower-tier champions)
    {"decay": 8,  "truncation": 0.05, "neutralization": "SUBINDUSTRY","universe": "TOP3000"},
    {"decay": 8,  "truncation": 0.05, "neutralization": "SECTOR",     "universe": "TOP3000"},
    # smaller universe (sub-universe SH protection has been a worry, but
    # maybe TOP1000 with low trunc retains SH)
    {"decay": 8,  "truncation": 0.02, "neutralization": "INDUSTRY",   "universe": "TOP1000"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_CHAMP_OPT.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, sv in enumerate(SETTINGS_GRID, 1):
        s = dict(BASE_SETTINGS); s.update(sv)
        tag = f"d{sv['decay']}_t{sv['truncation']}_{sv['neutralization'][:3]}_{sv['universe']}"
        log.info(f"=== opt {i}/{len(SETTINGS_GRID)} [{tag}]")
        r = submit(cm.session, CHAMPION_EXPR, s)
        r.tag = tag
        if r.ok:
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                     f"pass={r.all_checks_pass} ({r.checks_passed}/{r.checks_total}) "
                     f"alpha={r.alpha_id}")
        else:
            log.info(f"   ERR: {r.error[:160]}")
        results.append(r)
        out_path.write_text(json.dumps([asdict(x) for x in results], indent=2))

    ok = [r for r in results if r.ok]
    ready = [r for r in ok if r.all_checks_pass]
    print()
    print("=" * 100)
    print(f"champ-opt done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
