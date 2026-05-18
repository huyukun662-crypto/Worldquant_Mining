"""Champion × PV-derived signals miner.

Diversify discovered that vwap-close/close added to champion gave SH
2.70 / FIT 1.90 (the new best). News, social and fundamentals diluted.
Conclusion: PV-derived intraday-microstructure signals stack with the
model-factor champion. This module explores 12 more PV variants in
the same family - each is a classic alpha building block.

Run:
    python -m mining_pipeline.pv_combo_d1
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
log = logging.getLogger("pv-combo-d1")

REPO = Path(__file__).resolve().parent.parent

# Re-use submit machinery from diversify miner
from mining_pipeline.diversify_d1_miner import (
    CHAMPION, BASE_SETTINGS, submit, SimResult, _load, VENDOR
)


# 12 PV-derived "B" signals to combine with CHAMPION via rank-add.
# Each is a classic alpha building block in the price-volume space.
B_PV_SIGNALS: list[tuple[str, str]] = [
    # mean-reversion vs close
    ("vwap_close_pct",   "rank(divide(subtract(vwap, close), close))"),
    ("high_close_pct",   "rank(divide(subtract(high, close), close))"),
    ("close_low_pct",    "rank(divide(subtract(close, low), close))"),
    ("close_open_pct",   "rank(divide(subtract(close, open), open))"),
    # range / volatility
    ("range_close",      "rank(divide(subtract(high, low), close))"),
    ("range_open",       "rank(divide(subtract(high, low), open))"),
    # volume-pressure
    ("vol_rel_adv",      "rank(divide(volume, adv20))"),
    ("vol_log_rel_adv",  "rank(log(divide(volume, adv20)))"),
    # ts-smoothed micro
    ("ts_vwap_close_5",  "rank(ts_mean(divide(subtract(vwap, close), close), 5))"),
    ("ts_vwap_close_10", "rank(ts_mean(divide(subtract(vwap, close), close), 10))"),
    # short-term reversal on returns
    ("ts_ret_5_neg",     "-rank(ts_sum(returns, 5))"),
    ("ts_ret_3_neg",     "-rank(ts_sum(returns, 3))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_PV_COMBO.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    log.info(f"PV-combo scan: {len(B_PV_SIGNALS)} pairings × CHAMPION, "
             f"~{len(B_PV_SIGNALS)*120/60:.0f} min")

    out_path = REPO / args.out
    results = []
    for i, (tag, b) in enumerate(B_PV_SIGNALS, 1):
        combo = f"rank(({CHAMPION}) + ({b}))"
        log.info(f"=== pv {i}/{len(B_PV_SIGNALS)} [{tag}]")
        log.info(f"   B: {b}")
        r = submit(cm.session, combo, BASE_SETTINGS)
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
    print(f"pv-combo done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
