"""Structural variants miner: try DIFFERENT alpha shapes (not rank-add).

All prior families share the shape:
  rank((base_signal + novelty) + pv_micro)

This module tries fundamentally different shapes around proven base
signals:

  1. trade_when(condition, signal, -1) - signal only on high-vol days
  2. bucket(rank(signal), buckets="0,0.1,0.9,1.0") - extreme deciles
  3. signed_power(signal - 0.5, 3) - tail amplification
  4. group_neutralize(signal, market) - extra neutralization layer
  5. vector_neut(signal, cap) - cap-neutralize
  6. winsorize wrapper - outlier clip (skip rank chain)
  7. ts_decay_linear heavy smoothing
  8. trade_when with volume regime filter on champion

Run:
    python -m mining_pipeline.struct_variants
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
log = logging.getLogger("struct")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, _load, VENDOR
)


# Proven base signals (1-component, strong)
BASE_VWAP   = "rank(divide(subtract(vwap, close), close))"
BASE_TSRET3 = "-rank(ts_sum(returns, 3))"
BASE_VOL    = "rank(divide(volume, adv20))"
BASE_DFLC   = "-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"

# Family A core (model-based) - for use as input to structural wrappers
CHAMP_MODELS = (
    "rank((rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_chg12msip, 120), 20)))"
    " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_fangma_rvm_usa_fangma_rvm6, 120), 20))))))"
)


CANDIDATES: list[tuple[str, str]] = [
    # ---- 1. trade_when conditional ----
    # Trade vwap-close signal only when volume > adv20 (high attention days)
    ("trade_when_vol_vwap",
     f"trade_when(greater(volume, adv20), {BASE_VWAP}, -1)"),
    # Trade champion model signal only on high-volume days
    ("trade_when_vol_champ",
     f"trade_when(greater(volume, adv20), {CHAMP_MODELS}, -1)"),

    # ---- 2. bucket extreme deciles ----
    # Only trade the top 10% and bottom 10% on vwap-close
    ("bucket_extreme_vwap",
     f'bucket(rank(divide(subtract(vwap, close), close)), buckets="0.0,0.1,0.9,1.0")'),
    # Same on champion
    ("bucket_extreme_champ",
     f'bucket(rank({CHAMP_MODELS}), buckets="0.0,0.1,0.9,1.0")'),

    # ---- 3. signed_power tail amplification ----
    # Amplify the tails of the centered vwap signal
    ("signed_power_vwap",
     "signed_power(subtract(rank(divide(subtract(vwap, close), close)), 0.5), 3)"),

    # ---- 4. group_neutralize wrapper (extra layer beyond settings) ----
    # Market-neutralize the champion (above and beyond INDUSTRY)
    ("gneut_market_champ",
     f"group_neutralize({CHAMP_MODELS}, market)"),
    # Subindustry-neutralize the vwap+dflc combo
    ("gneut_subind_vwap_dflc",
     f"group_neutralize(rank(({BASE_VWAP}) + ({BASE_DFLC})), subindustry)"),

    # ---- 5. vector_neut against cap ----
    # Remove cap-bias from champion
    ("vneut_cap_champ",
     f"vector_neut({CHAMP_MODELS}, rank(cap))"),

    # ---- 6. winsorize directly (no rank chain) ----
    ("wins_only_vwap",
     "winsorize(divide(subtract(vwap, close), close), std=3)"),

    # ---- 7. ts_decay_linear heavy smoothing on raw vwap signal ----
    ("decay30_vwap",
     "rank(ts_decay_linear(divide(subtract(vwap, close), close), 30))"),

    # ---- 8. multi-condition trade_when ----
    # Trade only on days when volume > 2*adv20 AND price went up
    ("trade_2x_uptrend_vwap",
     f"trade_when(and(greater(volume, multiply(adv20, 2.0)), greater(returns, 0)), {BASE_VWAP}, -1)"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_STRUCT.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== struct {i}/{len(CANDIDATES)} [{tag}]")
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
    print(f"struct done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
