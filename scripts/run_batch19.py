"""Batch 19: exploit the neutralization tension on returns-120.
- NONE: SH 0.91 / FIT 1.63 / TO 0.067 -> lower decay to raise SH toward
  1.25 while keeping fitness headroom (and shorter horizons have higher SH).
- INDUSTRY: SH 1.28 / FIT 0.75 / TO 0.47 -> higher decay to cut TO and
  raise fitness while keeping SH > 1.25.
NONE/INDUSTRY also carry different exposures than the SUBINDUSTRY winner ->
likely more decorrelated."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(n, d):
    return settings("TOP1000", n, decay=d, trunc=0.08)

R = lambda n: f"rank(-ts_rank(returns, {n}))"

cands = [
    (R(120), st("NONE", 8)),
    (R(120), st("NONE", 4)),
    (R(90),  st("NONE", 8)),
    (R(60),  st("NONE", 8)),
    (R(120), st("INDUSTRY", 24)),
    (R(120), st("INDUSTRY", 32)),
    (R(90),  st("INDUSTRY", 24)),
    (R(150), st("NONE", 8)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch19.json", "w"), indent=2)
print("=== SAVED batch19.json ===")
