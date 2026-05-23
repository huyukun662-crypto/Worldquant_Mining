"""Family ANL + SENT: analyst-estimate and sentiment data categories.

Two more fresh data dimensions beyond model/PV/option:

ANALYST (EPS estimate revisions / dispersion - earnings expectation
alpha, classic and distinct from price):
  - EPS revision momentum: ts_delta(eps_mean)
  - estimate dispersion: (eps_high - eps_low) / |eps_mean|
  - coverage change: ts_delta(eps_number)
  - net-profit revision

SENTIMENT (news/social sentiment - behavioral alpha):
  - sentiment level / momentum (scl12_sentiment)
  - buzz spike (scl12_buzz z-score)
  - snt_value contrarian (note: snt_* are NEGATIVE-sentiment scores)

Each base is tested raw AND enriched with the proven dflc + vwap-close
backbone for fitness lift. The earnings-expectation and behavioral
signals are structurally independent from the model/PV/option families.

Run:
    python -m mining_pipeline.family_anl_sent
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
log = logging.getLogger("anl-sent")

REPO = Path(__file__).resolve().parent.parent

from mining_pipeline.diversify_d1_miner import (
    BASE_SETTINGS, submit, _load, VENDOR
)

DFLC = "-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"
VWAP = "rank(divide(subtract(vwap, close), close))"

# --- analyst primitives (ts_backfill 250: estimates update infrequently) ---
EPS_MEAN = "ts_backfill(anl4_afv4_eps_mean, 250)"
EPS_HIGH = "ts_backfill(anl4_afv4_eps_high, 250)"
EPS_LOW  = "ts_backfill(anl4_afv4_eps_low, 250)"
EPS_NUM  = "ts_backfill(anl4_afv4_eps_number, 250)"
NETPROF  = "ts_backfill(anl4_netprofit_value, 250)"

EPS_REVISION   = f"rank(ts_delta({EPS_MEAN}, 60))"                       # rising estimates bullish
EPS_DISPERSION = f"-rank(divide(subtract({EPS_HIGH}, {EPS_LOW}), abs({EPS_MEAN})))"  # high uncertainty bearish
COVERAGE_CHG   = f"rank(ts_delta({EPS_NUM}, 60))"                        # rising coverage
NETPROF_REV    = f"rank(ts_delta({NETPROF}, 60))"

# --- sentiment primitives ---
SENTIMENT = "ts_backfill(scl12_sentiment, 120)"
BUZZ      = "ts_backfill(scl12_buzz, 120)"
SNT_VALUE = "ts_backfill(snt_value, 120)"

SENT_LEVEL = f"rank({SENTIMENT})"
SENT_MOM   = f"rank(ts_delta({SENTIMENT}, 5))"
BUZZ_SPIKE = f"ts_zscore({BUZZ}, 22)"
SNT_CONTRA = f"rank({SNT_VALUE})"   # snt_value is NEGATIVE sentiment -> high = bearish crowd -> long


CANDIDATES: list[tuple[str, str]] = [
    # ===== ANALYST raw signals =====
    ("anl_eps_revision",    EPS_REVISION),
    ("anl_eps_dispersion",  EPS_DISPERSION),
    ("anl_coverage_chg",    COVERAGE_CHG),
    ("anl_netprof_rev",     NETPROF_REV),
    # analyst base = revision + dispersion
    ("anl_base",            f"rank(({EPS_REVISION}) + ({EPS_DISPERSION}))"),
    # enriched
    ("anl_revision_dflc_vwap",
     f"rank((rank(({EPS_REVISION}) + ({DFLC}))) + ({VWAP}))"),
    ("anl_base_dflc_vwap",
     f"rank((rank((rank(({EPS_REVISION}) + ({EPS_DISPERSION}))) + ({DFLC}))) + ({VWAP}))"),

    # ===== SENTIMENT raw signals =====
    ("snt_level",           SENT_LEVEL),
    ("snt_mom",             SENT_MOM),
    ("snt_buzz_spike",      BUZZ_SPIKE),
    ("snt_value_contra",    SNT_CONTRA),
    # sentiment base = momentum + contrarian
    ("snt_base",            f"rank(({SENT_MOM}) + ({SNT_CONTRA}))"),
    # enriched
    ("snt_mom_dflc_vwap",
     f"rank((rank(({SENT_MOM}) + ({DFLC}))) + ({VWAP}))"),
    ("snt_base_dflc_vwap",
     f"rank((rank((rank(({SENT_MOM}) + ({SNT_CONTRA}))) + ({DFLC}))) + ({VWAP}))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_ANL_SENT.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== as {i}/{len(CANDIDATES)} [{tag}]")
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
    print(f"anl-sent done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
