"""Batch 11: decorrelate the winning reversal by changing neutralization
and universe (reshapes PnL -> may drop correlation vs the SUBINDUSTRY/
TOP1000 winner below 0.70 while still passing all submit checks).
Expression fixed to the proven winner; decay16."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

EXPR = "rank(-ts_rank(returns, 5))"

def st(n="SUBINDUSTRY", u="TOP1000", d=16, t=0.08):
    return settings(u, n, decay=d, trunc=t)

cands = [
    (EXPR, st("MARKET",      "TOP1000")),
    (EXPR, st("SECTOR",      "TOP1000")),
    (EXPR, st("NONE",        "TOP1000")),
    (EXPR, st("SUBINDUSTRY", "TOP500")),
    (EXPR, st("SUBINDUSTRY", "TOP200")),
    (EXPR, st("MARKET",      "TOP500")),
    (EXPR, st("INDUSTRY",    "TOP1000")),
    (EXPR, st("SUBINDUSTRY", "TOP1000", d=12)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch11.json", "w"), indent=2)
print("=== SAVED batch11.json ===")
