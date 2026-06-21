"""Batch 21: get returns-250 over fitness 1.0. returns-250 decay24
SUBINDUSTRY = SH 1.54 / FIT 0.98 / corr 0.51 vs winner (well under 0.70).
Only 0.02 fitness short. Higher truncation concentrates positions ->
higher returns -> higher fitness; fine decay around 24."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d, t):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=t)

R = lambda n: f"rank(-ts_rank(returns, {n}))"

cands = [
    (R(250), cfg(24, 0.10)),
    (R(250), cfg(24, 0.12)),
    (R(250), cfg(24, 0.15)),
    (R(250), cfg(20, 0.12)),
    (R(250), cfg(28, 0.10)),
    (R(300), cfg(24, 0.10)),
    (R(280), cfg(24, 0.12)),
    (R(250), cfg(22, 0.15)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch21.json", "w"), indent=2)
print("=== SAVED batch21.json ===")
