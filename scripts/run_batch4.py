"""Batch 4: stronger anomalies -- analyst-revision / multi-factor momentum
derivatives (model16) and low-risk (model51). rank() probes sign."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

st = lambda u="TOP1000", n="SUBINDUSTRY", d=4: settings(u, n, decay=d)

cands = [
    ("rank(composite_factor_score_derivative)",          st()),
    ("rank(analyst_revision_rank_derivative)",           st()),
    ("rank(multi_factor_acceleration_score_derivative)", st()),
    ("rank(multi_factor_static_score_derivative)",       st()),
    ("rank(growth_potential_rank_derivative)",           st()),
    ("rank(relative_valuation_rank_derivative)",         st()),
    ("rank(beta_last_360_days_spy)",                     st()),
    ("rank(unsystematic_risk_last_360_days)",            st()),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch4.json", "w"), indent=2)
print("=== SAVED batch4.json ===")
