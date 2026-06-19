"""Batch 13: push the LOW-correlation long-horizon reversals over fitness
1.0. returns-120 has corr 0.61 vs the winner (< 0.70 self-corr limit) but
FIT 0.90; returns-40 corr 0.65 / FIT 0.84. Higher decay lifted fitness for
shorter horizons -> sweep higher decay (and a truncation bump) to clear
1.0 while staying decorrelated."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(d, t=0.08):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=t)

cands = [
    ("rank(-ts_rank(returns, 120))", st(24)),
    ("rank(-ts_rank(returns, 120))", st(32)),
    ("rank(-ts_rank(returns, 120))", st(48)),
    ("rank(-ts_rank(returns, 120))", st(24, t=0.12)),
    ("rank(-ts_rank(returns, 120))", st(16, t=0.15)),
    ("rank(-ts_rank(returns, 40))",  st(24)),
    ("rank(-ts_rank(returns, 40))",  st(32)),
    ("rank(-ts_rank(returns, 60))",  st(32)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch13.json", "w"), indent=2)
print("=== SAVED batch13.json ===")
