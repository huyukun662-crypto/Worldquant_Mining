"""Batch 31: push the NEW zscore-reversal structure over FIT 1.0.
normalize(-ts_zscore(returns,7)) decay18 = SH 1.92 / FIT 0.99 -- a different
operator (ts_zscore vs ts_rank), just 0.01 short. Sweep horizon 5-8 x decay
16-22 to clear fitness. Vol-scaled reversal (divide by std) was too weak."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

Z = lambda n: f"normalize(-ts_zscore(returns, {n}))"

def cfg(d):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    (Z(7), cfg(16)),
    (Z(7), cfg(20)),
    (Z(7), cfg(22)),
    (Z(6), cfg(18)),
    (Z(6), cfg(16)),
    (Z(8), cfg(18)),
    (Z(8), cfg(20)),
    (Z(5), cfg(18)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch31.json", "w"), indent=2)
print("=== SAVED batch31.json ===")
