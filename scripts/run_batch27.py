"""Batch 27: add MARGIN to the low-correlation submittable factor
normalize(-ts_rank(returns,250)) decay24 (corr 0.50, FIT exactly 1.0,
sub-universe SH 0.83 vs 0.81 -- both tight). Sweep decay/horizon/trunc
around it to find a config with FIT comfortably >1.0 and more sub-universe
headroom, while keeping correlation < 0.70."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d, t=0.08):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=t)

N = "normalize(-ts_rank(returns, {n}))"

cands = [
    (N.format(n=250), cfg(20)),
    (N.format(n=250), cfg(22)),
    (N.format(n=250), cfg(28)),
    (N.format(n=250), cfg(24, 0.12)),
    (N.format(n=200), cfg(24)),
    (N.format(n=300), cfg(24)),
    (N.format(n=220), cfg(22)),
    (N.format(n=250), cfg(16)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch27.json", "w"), indent=2)
print("=== SAVED batch27.json ===")
