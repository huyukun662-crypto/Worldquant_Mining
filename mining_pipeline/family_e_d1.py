"""Family E miner: deep value + liquidity risk pair.

Families used so far:
  A: chg12msip + fangma_rvm6
  B: ttmocfev + relativevaluemodel_ttmfcfp
  D: shortsentiment + garp_analyst_capeff
  C: pure PV+novelty

Family E base = deep value (mdl177_2_deepvaluefactor_curep)
              + liquidity (mdl177_2_liquidityriskfactor_si_ratio)

These two are conceptually orthogonal to A/B/D (value vs short interest)
so the family should have low correlation to existing alphas.

Run:
    python -m mining_pipeline.family_e_d1
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
log = logging.getLogger("family-e")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, SimResult, _load, VENDOR
)

# Family E base - deepvalue + liquidity-risk (both with ts_av_diff for trend)
# Scan signs: deepvaluefactor_curep was rank-style flipped (use -av_diff)
#             liquidityriskfactor_si_ratio was rank_neg form
E_BASE = (
    "rank((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_deepvaluefactor_curep, 120), 20))))"
    " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_2_liquidityriskfactor_si_ratio, 120), 20))))))"
)

DFLC      = "-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"
VWAP_DIFF = "rank(divide(subtract(vwap, close), close))"
VOL_REL   = "rank(divide(volume, adv20))"
TS_RET3   = "-rank(ts_sum(returns, 3))"


CANDIDATES: list[tuple[str, str]] = [
    # (tag, expression)
    ("e_base",
     E_BASE),
    ("e_base_dflc",
     f"rank(({E_BASE}) + ({DFLC}))"),
    ("e_dflc_vwap",
     f"rank((rank(({E_BASE}) + ({DFLC}))) + ({VWAP_DIFF}))"),
    ("e_dflc_tsret3",
     f"rank((rank(({E_BASE}) + ({DFLC}))) + ({TS_RET3}))"),
    ("e_dflc_vol",
     f"rank((rank(({E_BASE}) + ({DFLC}))) + ({VOL_REL}))"),
    ("e_full",
     f"rank((rank((rank((rank(({E_BASE}) + ({DFLC}))) + ({VWAP_DIFF}))) + ({TS_RET3}))) + ({VOL_REL}))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_FAMILY_E.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== e {i}/{len(CANDIDATES)} [{tag}]")
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
    print(f"family-e done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
