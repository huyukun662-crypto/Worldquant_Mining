"""Pure-PV family miner: third independent alpha lineage.

Families A and B both use model factors (mdl177_*). Family C should
use ONLY price-volume / micro-structure signals so it's orthogonal to
both. Goal: 3 alphas that can ALL pass SELF_CORRELATION at submit time.

Builds combos of: vwap-close micro, vol/adv liquidity, short-term
reversal (ts_sum returns), high-low range, dflc on revere_index_value
(reused since it's a novelty signal not a model factor).

Run:
    python -m mining_pipeline.pure_pv_family
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
log = logging.getLogger("pure-pv")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, SimResult, _load, VENDOR
)


# Pure-PV building blocks
VWAP_DIFF = "rank(divide(subtract(vwap, close), close))"
VOL_REL   = "rank(divide(volume, adv20))"
TS_RET3   = "-rank(ts_sum(returns, 3))"
TS_RET5   = "-rank(ts_sum(returns, 5))"
TS_RET10  = "-rank(ts_sum(returns, 10))"
HL_RANGE  = "rank(divide(subtract(high, low), close))"
# Reuse dflc as novelty (no model factors)
DFLC      = "-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"


CANDIDATES: list[tuple[str, str]] = [
    # All-PV combos (no model factors)
    ("pv_vwap_tsret3",
     f"rank(({VWAP_DIFF}) + ({TS_RET3}))"),
    ("pv_vwap_tsret5",
     f"rank(({VWAP_DIFF}) + ({TS_RET5}))"),
    ("pv_vwap_vol",
     f"rank(({VWAP_DIFF}) + ({VOL_REL}))"),
    ("pv_vwap_tsret3_dflc",
     f"rank((rank(({VWAP_DIFF}) + ({TS_RET3}))) + ({DFLC}))"),
    ("pv_vwap_vol_dflc",
     f"rank((rank(({VWAP_DIFF}) + ({VOL_REL}))) + ({DFLC}))"),
    ("pv_full",
     f"rank((rank((rank(({VWAP_DIFF}) + ({TS_RET3}))) + ({VOL_REL}))) + ({DFLC}))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_PURE_PV.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== pv-fam {i}/{len(CANDIDATES)} [{tag}]")
        log.info(f"   expr: {expr[:140]}")
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
    print(f"pure-pv done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
