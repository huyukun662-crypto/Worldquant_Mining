"""Batch 36: group_rank reversal -> submittable. group_rank(-returns,
subindustry) passed SH 1.51 (FIT 0.74) -- a structurally different operator
(within-group ranking) from plain rank+neutralize. Combine with the ts_rank
reversal and normalize/decay to lift fitness over 1.0 across group levels."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d=18):
    # neutralization NONE since group_rank already does cross-group ranking
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

R7 = "-ts_rank(returns, 7)"
cands = [
    (f"normalize(group_rank({R7}, subindustry))",       cfg(18)),
    (f"normalize(group_rank({R7}, industry))",          cfg(18)),
    (f"normalize(group_rank({R7}, sector))",            cfg(18)),
    (f"normalize(group_rank(-ts_rank(returns, 5), subindustry))", cfg(18)),
    (f"normalize(group_rank(-ts_rank(returns, 10), subindustry))", cfg(20)),
    (f"normalize(group_neutralize({R7}, subindustry))", cfg(18)),
    (f"normalize(group_rank(-returns, subindustry))",   cfg(18)),
    (f"group_rank({R7}, subindustry)",                  cfg(18)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch36.json", "w"), indent=2)
print("=== SAVED batch36.json ===")
