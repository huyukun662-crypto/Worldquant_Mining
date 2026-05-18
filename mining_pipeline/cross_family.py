"""Cross-family combo: pair-rank-add of family champions.

We have 5 effective families (A, B, C, D, E). Each family's champion
is a 4-component combo. This module tests pair combinations of
champions across families, producing 6-component meta-alphas. If two
champion alphas have correlation ~0.5, combined should have:
  SH_combined ~ SH_each * sqrt(2 / (1 + 0.5)) ~ 1.15 * SH_each

So champion A (SH 2.70) + champion C (SH 2.50) might produce SH ~3.0.

Run:
    python -m mining_pipeline.cross_family
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from itertools import combinations
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cross-family")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, SimResult, _load, VENDOR
)


# Family champions (the strongest pass=True per family)
CHAMPIONS = {
    "A_blNxvooZ": (
        # SH 2.70 FIT 1.90
        "rank((rank((rank((rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_chg12msip, 120), 20)))"
        " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_fangma_rvm_usa_fangma_rvm6, 120), 20))))))) "
        "+ (-1 * (rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60))))))) "
        "+ (rank(divide(subtract(vwap, close), close))))"
    ),
    "B_N1nK7RPw": (
        # SH 2.57 FIT 1.88
        "rank((rank((rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_ttmocfev, 120), 20)))))"
        " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_relativevaluemodel_ttmfcfp, 120), 20))))))) "
        "+ (-1 * (rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60))))))) "
        "+ (rank(divide(subtract(vwap, close), close))))"
    ),
    "C_2rvGjMd5": (
        # SH 2.50 FIT 1.96 (pure PV, no model)
        "rank((rank((rank((rank(divide(subtract(vwap, close), close))) "
        "+ (-rank(ts_sum(returns, 3))))) + (rank(divide(volume, adv20))))) "
        "+ (-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))))"
    ),
    "D_vR5YYLKr": (
        # SH 2.32 FIT 1.54
        "rank((rank((rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_5shortsentimentfactor_act_util, 120), 20))))"
        " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_garpanalystmodel_qgp_capeff, 120), 20))))))) "
        "+ (-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))))) "
        "+ (rank(divide(subtract(vwap, close), close))))"
    ),
    "E_pwnWMgPx": (
        # SH 1.84 FIT 1.15
        "rank((rank((rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_deepvaluefactor_curep, 120), 20))))"
        " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_liquidityriskfactor_si_ratio, 120), 20))))))) "
        "+ (-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))))) "
        "+ (rank(divide(subtract(vwap, close), close))))"
    ),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_CROSS.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    # Skip A+B and B+A (commutative); keep all 10 unique pairs.
    keys = list(CHAMPIONS.keys())
    pairs = list(combinations(keys, 2))
    log.info(f"cross-family scan: {len(pairs)} unique pairs, "
             f"~{len(pairs)*120/60:.0f} min")

    out_path = REPO / args.out
    results = []
    for i, (a, b) in enumerate(pairs, 1):
        expr = f"rank(({CHAMPIONS[a]}) + ({CHAMPIONS[b]}))"
        tag = f"{a[:1]}_x_{b[:1]}"
        log.info(f"=== cross {i}/{len(pairs)} [{tag}] = {a} × {b}")
        r = submit(cm.session, expr, BASE_SETTINGS)
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
    print(f"cross-family done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
