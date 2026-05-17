"""v8: break SH=1.30 ceiling with NEW fields and operators.

After 7 runs / 313 trials on PV-only with limited operators, the
champion family ceilings at SH=1.30. v8 brings in:

NEW FIELDS (from constants/data_fields_USA_TOP3000_D0_PV.json):
  rel_ret_comp / rel_ret_cust / rel_ret_part -- competitor / customer
    / supplier relationship returns (independent signal source)
  pv13_*  -- 22 sector-themed PV13 features
  dividend, split -- corporate-action events

NEW OPERATORS (from constants/upstream_operatorRAW.json):
  vector_neut(x, y)   -- residualize x against y (orthogonalization)
  ts_regression(y, x, d) -- rolling beta
  ts_arg_max(x, d)    -- index of max
  if_else(cond, t, f) -- regime branching
  group_mean / group_max -- new group ops
  hump(x, h)          -- jump dampener
"""
from __future__ import annotations
import json, sys, logging
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mining_pipeline import wq_pipeline as W

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v8")


def wrap(core):
    return f"scale(ts_backfill(winsorize({core}, std=4), 5))"


CANDIDATES = [
    # 1. Pure relationship signal: competitor's recent return as alpha
    wrap("rel_ret_comp"),

    # 2. Customer's recent return -- supply-chain lead
    wrap("rel_ret_cust"),

    # 3. Supplier's recent return
    wrap("rel_ret_part"),

    # 4. PV13 small-sector pre-computed alpha
    wrap("pv13_h_min10_all_sector"),

    # 5. Another PV13 variant
    wrap("pv13_h_min2_focused_sector"),

    # 6. vector_neut: champion signal orthogonalized against market returns
    wrap("vector_neut(multiply(subtract(ts_std_dev(high, 39), ts_rank(adv20, 31)), "
         "ts_std_dev(multiply(cap, open), 18)), returns)"),

    # 7. ts_regression: rolling beta of close against returns
    wrap("ts_regression(close, returns, 60)"),

    # 8. if_else regime: use rel_ret_comp on up days, neg on down days
    wrap("if_else(greater(returns, 0), rel_ret_comp, multiply(rel_ret_comp, -1))"),

    # 9. ts_arg_max: index of max return in 20d window (recency-of-high)
    wrap("ts_arg_max(returns, 20)"),

    # 10. group_mean: rel_ret_comp averaged within sector
    "scale(ts_backfill(group_mean(rel_ret_comp, sector), 5))",
]


def main():
    out_path = REPO / "WQ_D0_V8_NEW_FIELDS_OPS_REPORT.json"

    cm_mod = W._load(W.VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"auth ok as {cm.credentials.username}")

    W.SETTING_SPACE["delay"] = [0]
    n_trials = 3
    base_seed = 919

    all_results = []
    for i, expr in enumerate(CANDIDATES, 1):
        log.info(f"=== [{i}/{len(CANDIDATES)}] candidate: {expr}")
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
