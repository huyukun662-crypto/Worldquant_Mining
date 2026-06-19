"""Batch 9: push the 10- and 22-horizon ts_rank reversals over fitness 1.0.
At decay16: returns-10 -> FIT 0.93, returns-22 -> FIT 0.95. For the
returns-5 winner, higher decay raised both Sharpe and fitness, so sweep
higher decay. These are lower-correlated diversifiers vs the returns-5
winner (different horizon)."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(d):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    ("rank(-ts_rank(returns, 10))", st(20)),
    ("rank(-ts_rank(returns, 10))", st(24)),
    ("rank(-ts_rank(returns, 10))", st(32)),
    ("rank(-ts_rank(returns, 22))", st(20)),
    ("rank(-ts_rank(returns, 22))", st(24)),
    ("rank(-ts_rank(returns, 22))", st(32)),
    ("rank(-ts_rank(returns, 10))", st(12)),
    ("rank(-ts_rank(returns, 22))", st(12)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch9.json", "w"), indent=2)
print("=== SAVED batch9.json ===")
