"""Stage 1c: curated, economically-motivated, STRUCTURALLY-DISTINCT D1 ideas.

The random v2 sweep produced only weak signals, so this submits a small,
hand-curated set of slow (low-turnover) factor STRUCTURES that differ from
the first winner (price-volume correlation + short reversal). All PV +
slow fundamentals (cap, sharesout); NO implied-volatility/option fields;
no ts_min/ts_max/ts_regression (inaccessible on this account tier).

Families (sign learned empirically by the simulator):
  M  long-horizon price momentum          ts_delta(close, 240)
  H  recency of rolling high (52w-high)    ts_arg_max(close, 240)
  I  net share issuance / dilution         ts_delta(sharesout, 120)
  T  share turnover (volume / sharesout)   volume / sharesout
  A  Amihud illiquidity |ret|/$vol         abs(returns)/(close*volume)
  G  overnight gap reversal                open / ts_delay(close, 1)
  V  VWAP positioning                      close / vwap   (best v2 signal)
  L  idiosyncratic low volatility          ts_std_dev(returns, 120)

Usage:  python scripts/mine_d1_v3.py
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mine-d1-v3")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

_spec = importlib.util.spec_from_file_location("mine_d1", REPO / "scripts" / "mine_d1.py")
mine_d1 = importlib.util.module_from_spec(_spec); sys.modules["mine_d1"] = mine_d1
_spec.loader.exec_module(mine_d1)

# Curated candidates (cross-sectional wrapped; sign learned by simulator).
CANDIDATES = [
    ("M_momentum_240",  "rank(ts_delta(close, 240))"),
    ("M_momentum_120",  "rank(ts_delta(close, 120))"),
    ("H_argmax_240",    "rank(ts_arg_max(close, 240))"),
    ("I_issuance_120",  "rank(ts_delta(sharesout, 120))"),
    ("T_turnover_60",   "rank(ts_mean(divide(volume, sharesout), 60))"),
    ("A_amihud_60",     "rank(ts_mean(divide(abs(returns), multiply(close, volume)), 60))"),
    ("G_gap_rev_20",    "rank(ts_mean(divide(open, ts_delay(close, 1)), 20))"),
    ("V_vwap_pos_10",   "rank(ts_mean(divide(close, vwap), 10))"),
    ("L_lowvol_120",    "rank(ts_std_dev(returns, 120))"),
    ("L_lowvol_240",    "rank(ts_std_dev(returns, 240))"),
]

BASE = {"universe": "TOP3000", "neutralization": "SUBINDUSTRY",
        "truncation": 0.08, "decay": 6}


def main():
    cm = mine_d1._load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
        base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    results = []
    for i, (name, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== [{i}/{len(CANDIDATES)}] {name}: {expr}")
        r = mine_d1.submit(cm.session, expr, BASE)
        rd = asdict(r); rd["name"] = name
        results.append(rd)
        if r.ok:
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                     f"DD={r.drawdown:.3f} sub={r.submittable} fail={r.failed_checks}")
        else:
            log.info(f"   [{r.error[:90]}]")
        json.dump(results, open(REPO / "WQ_D1_V3_REPORT.json", "w"), indent=2)
        time.sleep(2)

    ok = [r for r in results if r["ok"]]
    ok.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    print("\n" + "=" * 90)
    for r in ok:
        print(f"{r['sharpe']:+6.2f} TO={r['turnover']:.3f} DD={r['drawdown']:.3f} "
              f"sub={r['submittable']}  {r['name']:16} {r['expression'][:45]}")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
