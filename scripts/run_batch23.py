"""Batch 23: find a SUBMITTABLE reversal on a non-TOP3000 universe.
batch22 found TOPSP500 (returns-5 decay16: SH 1.80 / FIT 0.76) and TOP500
(returns-10 decay16: SH 1.72 / FIT 0.85) are the promising universes. Same
recipe as TOP1000: longer horizon + decay lifts fitness; TOPSP500's SH 1.8
gives headroom to clear fitness 1.0."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

R = lambda n: f"rank(-ts_rank(returns, {n}))"

cands = [
    (R(10), settings("TOPSP500", "SUBINDUSTRY", decay=16)),
    (R(10), settings("TOPSP500", "SUBINDUSTRY", decay=24)),
    (R(22), settings("TOPSP500", "SUBINDUSTRY", decay=16)),
    (R(5),  settings("TOPSP500", "SUBINDUSTRY", decay=24)),
    (R(10), settings("TOP500",   "SUBINDUSTRY", decay=24)),
    (R(22), settings("TOP500",   "SUBINDUSTRY", decay=16)),
    (R(22), settings("TOP500",   "SUBINDUSTRY", decay=24)),
    (R(40), settings("TOPSP500", "SUBINDUSTRY", decay=16)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch23.json", "w"), indent=2)
print("=== SAVED batch23.json ===")
