"""Try 10 distinct signal families to break the SH=1.30 ceiling.

Each candidate is wrapped in the proven scaffold (works on A1nGR0GW):
    scale(ts_backfill(winsorize(<signal>, std=4), 5))

Optuna tunes the integer windows. The signal cores themselves are
new -- different combinations of PV fields than the v4 champion's
realized-range / cap-weighted dispersion construction.
"""
from __future__ import annotations
import json, sys, logging
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mining_pipeline import wq_pipeline as W

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v7")


def wrap(core):
    return f"scale(ts_backfill(winsorize({core}, std=4), 5))"


SIGNALS = [
    # 1. flow-weighted momentum: buy volume * 1-day return
    wrap("multiply(ts_delta(close, 1), volume)"),

    # 2. vwap deviation (intraday flow vs close)
    wrap("divide(subtract(close, vwap), vwap)"),

    # 3. intraday range as vol proxy
    wrap("divide(subtract(high, low), close)"),

    # 4. ts_corr(returns, volume) -- price-flow alignment
    wrap("ts_corr(returns, volume, 20)"),

    # 5. sharesout flow * cap (buyback / issuance dollar size)
    wrap("multiply(ts_delta(sharesout, 5), cap)"),

    # 6. relative volume (today vs 20-day avg)
    wrap("divide(volume, adv20)"),

    # 7. low-vol anomaly: invert vol rank
    wrap("reverse(ts_std_dev(returns, 20))"),

    # 8. jump risk: |returns| / sigma
    wrap("divide(abs(returns), ts_std_dev(returns, 20))"),

    # 9. price-vwap coherence (close vs vwap correlation)
    wrap("ts_corr(vwap, close, 5)"),

    # 10. short-term reversal
    wrap("reverse(ts_mean(returns, 5))"),
]


def main():
    out_path = REPO / "WQ_D0_V7_SIGNAL_FAMILY_REPORT.json"

    cm_mod = W._load(W.VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"auth ok as {cm.credentials.username}")

    W.SETTING_SPACE["delay"] = [0]
    n_trials = 3
    base_seed = 829

    all_results = []
    for i, expr in enumerate(SIGNALS, 1):
        log.info(f"=== [{i}/{len(SIGNALS)}] signal: {expr}")
        rs = W.search_one(cm.session, expr, n_trials, base_seed + i)
        all_results.extend(rs)
        with open(out_path, "w") as f:
            json.dump([asdict(r) for r in all_results], f, indent=2)

    surv = [r for r in all_results if r.ok and r.sharpe > 2.0
            and r.turnover < 0.7 and r.turnover > 0.01 and r.fitness > 1.3]
    print()
    print("=" * 100)
    print(f"Total: {len(all_results)}, OK: {sum(1 for r in all_results if r.ok)}, "
          f"Submit-eligible (SH>2.0 TO in [0.01,0.7] FIT>1.3): {len(surv)}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
