"""Family OPT miner: option-derived D1 alphas (fresh data category).

The prior 57 submit-ready alphas all draw from model factors + PV +
novelty. This module opens an ENTIRELY new data dimension: the option
category (138 fields, untouched). Option-implied signals reflect
forward-looking positioning and are structurally uncorrelated to
price-volume and model-factor alphas.

Classic option alpha concepts built here:
  - PCR (put/call open-interest ratio) contrarian
  - IV skew  (put IV - call IV) = fear gauge
  - Vol risk premium (implied - historical vol)
  - IV term-structure slope (long tenor - short tenor)
  - IV momentum (ts_delta of IV)

Option fields have ~0.70 coverage (options-listed names skew large-cap),
so ts_backfill + pasteurization handle the 30% NaN. Each base option
signal is also enriched with the proven dflc + vwap-close backbone to
lift fitness.

Run:
    python -m mining_pipeline.family_opt_d1
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
log = logging.getLogger("family-opt")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, _load, VENDOR
)

# Proven backbone signals (shared with other families for fitness lift)
DFLC      = "-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"
VWAP_DIFF = "rank(divide(subtract(vwap, close), close))"

# Option-derived primitives (ts_backfill 250 since options data is sparse)
PCR        = "ts_backfill(pcr_oi_270, 250)"
IV_CALL270 = "ts_backfill(implied_volatility_call_270, 250)"
IV_PUT270  = "ts_backfill(implied_volatility_put_270, 250)"
IV_MEAN10  = "ts_backfill(implied_volatility_mean_10, 250)"
IV_MEAN120 = "ts_backfill(implied_volatility_mean_120, 250)"
IV_CALL30  = "ts_backfill(implied_volatility_call_30, 250)"
IV_CALL1080= "ts_backfill(implied_volatility_call_1080, 250)"
HV120      = "ts_backfill(historical_volatility_120, 250)"


# Composite option signals
PCR_CONTRARIAN = f"-rank({PCR})"                                       # high PCR -> bearish crowd -> fade
IV_SKEW        = f"rank(subtract({IV_PUT270}, {IV_CALL270}))"          # put IV - call IV (fear)
VRP            = f"rank(subtract({IV_MEAN120}, {HV120}))"              # implied - realized vol premium
IV_TERM        = f"rank(subtract({IV_CALL1080}, {IV_CALL30}))"        # term-structure slope
IV_MOM         = f"-rank(ts_delta({IV_MEAN10}, 5))"                    # IV momentum (mean-revert)


CANDIDATES: list[tuple[str, str]] = [
    # ---- raw option signals (find which carry alpha) ----
    ("opt_pcr",            PCR_CONTRARIAN),
    ("opt_iv_skew",        IV_SKEW),
    ("opt_vrp",            VRP),
    ("opt_iv_term",        IV_TERM),
    ("opt_iv_mom",         IV_MOM),

    # ---- option base = skew + vrp (two orthogonal option signals) ----
    ("opt_base",
     f"rank(({IV_SKEW}) + ({VRP}))"),

    # ---- enriched with backbone (dflc + vwap) ----
    ("opt_skew_dflc_vwap",
     f"rank((rank(({IV_SKEW}) + ({DFLC}))) + ({VWAP_DIFF}))"),
    ("opt_vrp_dflc_vwap",
     f"rank((rank(({VRP}) + ({DFLC}))) + ({VWAP_DIFF}))"),
    ("opt_pcr_dflc_vwap",
     f"rank((rank(({PCR_CONTRARIAN}) + ({DFLC}))) + ({VWAP_DIFF}))"),
    ("opt_base_dflc_vwap",
     f"rank((rank((rank(({IV_SKEW}) + ({VRP}))) + ({DFLC}))) + ({VWAP_DIFF}))"),
    ("opt_full",
     f"rank((rank((rank((rank(({IV_SKEW}) + ({VRP}))) + ({DFLC}))) + ({VWAP_DIFF}))) + ({PCR_CONTRARIAN}))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_FAMILY_OPT.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== opt {i}/{len(CANDIDATES)} [{tag}]")
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
    print(f"family-opt done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
