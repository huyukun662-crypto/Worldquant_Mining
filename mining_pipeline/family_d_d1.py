"""Family D miner: sentiment + analyst model pair.

Families A (chg12msip+fangma_rvm6) and B (ttmocfev+ttmfcfp) are
exhausted. This module builds Family D using the next-strongest
unused model pair from the original scan:

  base D = (5shortsentimentfactor_act_util) + (garpanalystmodel_qgp_capeff)

Original scan: both gave |SH| ~0.7-0.95 stand-alone, so combined
should land near SH 1.2-1.5 before dflc/vwap enrichment.

Run:
    python -m mining_pipeline.family_d_d1
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
log = logging.getLogger("family-d")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, SimResult, _load, VENDOR
)

# Family D base - shortsentiment + garp-analyst (lower-tier but unused)
# Both flipped to positive form based on scan signs.
D_BASE = (
    "rank((rank(ts_backfill(mdl177_5shortsentimentfactor_act_util, 120)))"
    " + ((-1 * (rank(ts_backfill(mdl177_2_garpanalystmodel_qgp_capeff, 120))))))"
)

# Same novelty + PV building blocks
DFLC      = "-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"
VWAP_DIFF = "rank(divide(subtract(vwap, close), close))"
VOL_REL   = "rank(divide(volume, adv20))"
TS_RET3   = "-rank(ts_sum(returns, 3))"


CANDIDATES: list[tuple[str, str]] = [
    # (tag, expression)
    ("d_base",
     D_BASE),
    ("d_base_av_diff",
     # Try ts_av_diff form like A/B (the original scan used static rank)
     "rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_5shortsentimentfactor_act_util, 120), 20))))"
     " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_garpanalystmodel_qgp_capeff, 120), 20))))))"),
    ("d_base_dflc",
     f"rank(({D_BASE}) + ({DFLC}))"),
    ("d_avd_dflc",
     # ts_av_diff D-base + dflc
     "rank((rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_5shortsentimentfactor_act_util, 120), 20))))"
     " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_garpanalystmodel_qgp_capeff, 120), 20))))))) "
     f"+ ({DFLC}))"),
    ("d_avd_dflc_vwap",
     # The full stack: D-av_diff + dflc + vwap
     "rank((rank((rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_5shortsentimentfactor_act_util, 120), 20))))"
     " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_garpanalystmodel_qgp_capeff, 120), 20))))))) "
     f"+ ({DFLC}))) + ({VWAP_DIFF}))"),
    ("d_avd_dflc_tsret3",
     "rank((rank((rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_5shortsentimentfactor_act_util, 120), 20))))"
     " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_garpanalystmodel_qgp_capeff, 120), 20))))))) "
     f"+ ({DFLC}))) + ({TS_RET3}))"),
    ("d_full",
     "rank((rank((rank((rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_5shortsentimentfactor_act_util, 120), 20))))"
     " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_garpanalystmodel_qgp_capeff, 120), 20))))))) "
     f"+ ({DFLC}))) + ({VWAP_DIFF}))) + ({TS_RET3}))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_FAMILY_D.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== d {i}/{len(CANDIDATES)} [{tag}]")
        log.info(f"   expr: {expr[:160]}")
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
    print(f"family-d done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
