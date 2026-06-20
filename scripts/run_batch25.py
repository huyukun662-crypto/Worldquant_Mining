"""Batch 25: more TOP1000 factors with Fitness >= 1.0 (constraint relaxed to
just TOP1000 + FIT>=1, correlation no longer required). The winner
returns-5 decay16 hit 1.01; nearby reversal configs (returns 4-10, decay
12-26) should also cross 1.0, giving a set of submittable TOP1000 factors.
returns-10 decay24 was 0.99 -- push it over."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

R = lambda n: f"rank(-ts_rank(returns, {n}))"

def cfg(d, t=0.08):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=t)

cands = [
    (R(5),  cfg(20)),
    (R(6),  cfg(18)),
    (R(7),  cfg(18)),
    (R(8),  cfg(20)),
    (R(10), cfg(22)),
    (R(10), cfg(26)),
    (R(4),  cfg(14)),
    (R(5),  cfg(14)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch25.json", "w"), indent=2)
print("=== SAVED batch25.json ===")
