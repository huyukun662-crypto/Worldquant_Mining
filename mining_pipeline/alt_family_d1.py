"""Alternative-family miner: build a second independent alpha lineage.

Our 27 submit-ready alphas all share the same parent base
(chg12msip - fangma_rvm6). At click-Submit time, SELF_CORRELATION runs
against the user's already-submitted pool - one alpha entering means
the rest will likely correlate-fail.

This module builds a *parallel* alpha family using a different model-
field pair (ttmocfev + relativevaluemodel_ttmfcfp) + dflc + the
discovered PV winners. Goal: produce alphas with low pairwise
correlation to the champion family so we can submit BOTH.

Run:
    python -m mining_pipeline.alt_family_d1
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
log = logging.getLogger("alt-family")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, SimResult, _load, VENDOR
)

# Alternative base: ttmocfev + relativevaluemodel_ttmfcfp instead of
# chg12msip + fangma_rvm6. Same idiom (ts_av_diff, 20-day window,
# rank-add) but different parent factors -> orthogonal alpha family.
ALT_BASE = (
    "rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_ttmocfev, 120), 20))))"
    " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_relativevaluemodel_ttmfcfp, 120), 20))))))"
)

# Same novelty / PV signals as in the champion family
DFLC      = "-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"
VWAP_DIFF = "rank(divide(subtract(vwap, close), close))"
VOL_REL   = "rank(divide(volume, adv20))"
TS_RET3   = "-rank(ts_sum(returns, 3))"


CANDIDATES: list[tuple[str, str]] = [
    # (tag, expression)
    ("alt_base",
     ALT_BASE),
    ("alt_base_plus_dflc",
     f"rank(({ALT_BASE}) + ({DFLC}))"),
    ("alt_dflc_plus_vwap",
     f"rank((rank(({ALT_BASE}) + ({DFLC}))) + ({VWAP_DIFF}))"),
    ("alt_dflc_plus_vol",
     f"rank((rank(({ALT_BASE}) + ({DFLC}))) + ({VOL_REL}))"),
    ("alt_dflc_plus_tsret3",
     f"rank((rank(({ALT_BASE}) + ({DFLC}))) + ({TS_RET3}))"),
    ("alt_full_combo",
     f"rank((rank((rank(({ALT_BASE}) + ({DFLC}))) + ({VWAP_DIFF}))) + ({TS_RET3}))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_ALT_FAMILY.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== alt {i}/{len(CANDIDATES)} [{tag}]")
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
    print(f"alt-family done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
