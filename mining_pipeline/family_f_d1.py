"""Family F miner: alternative-anchor stack (NO dflc, NO vwap-close).

Families A/B/C/D/E all share the dflc + vwap-close + ts_ret backbone.
Family F deliberately swaps those for alternative novelty / micro
signals so it's structurally independent and should pass
SELF_CORRELATION even after other families are submitted.

Building blocks (all different from prior families):
  novelty_alt  : -rank(last_diff_value(pv13_custretsig_retsig, 30))
  micro_alt    : rank((high - low) / open)        [intraday range/open]
  mr_alt       : -rank(divide(close, ts_mean(close, 20)))  [mean revert]
  vol_alt      : rank(ts_zscore(volume, 22))      [vol z-score]
  cap_alt      : rank(log(cap))                   [size factor]

Each candidate combines 2-3 of these for variation.

Run:
    python -m mining_pipeline.family_f_d1
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
log = logging.getLogger("family-f")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, SimResult, _load, VENDOR
)

NOVELTY_ALT = "-rank(last_diff_value(ts_backfill(pv13_custretsig_retsig, 60), 30))"
MICRO_ALT   = "rank(divide(subtract(high, low), open))"
MR_ALT      = "-rank(divide(close, ts_mean(close, 20)))"
VOL_ALT     = "rank(ts_zscore(volume, 22))"
CAP_ALT     = "rank(log(cap))"


CANDIDATES: list[tuple[str, str]] = [
    # (tag, expression)
    ("f_micro_novelty",
     f"rank(({MICRO_ALT}) + ({NOVELTY_ALT}))"),
    ("f_micro_mr",
     f"rank(({MICRO_ALT}) + ({MR_ALT}))"),
    ("f_mr_vol",
     f"rank(({MR_ALT}) + ({VOL_ALT}))"),
    ("f_micro_novelty_mr",
     f"rank((rank(({MICRO_ALT}) + ({NOVELTY_ALT}))) + ({MR_ALT}))"),
    ("f_micro_mr_vol",
     f"rank((rank(({MICRO_ALT}) + ({MR_ALT}))) + ({VOL_ALT}))"),
    ("f_full",
     f"rank((rank((rank(({MICRO_ALT}) + ({NOVELTY_ALT}))) + ({MR_ALT}))) + ({VOL_ALT}))"),
    # cap weighting variants
    ("f_micro_cap",
     f"rank(({MICRO_ALT}) + ({CAP_ALT}))"),
    ("f_mr_cap",
     f"rank(({MR_ALT}) + ({CAP_ALT}))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_FAMILY_F.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== f {i}/{len(CANDIDATES)} [{tag}]")
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
    print(f"family-f done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
