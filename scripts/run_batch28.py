"""Batch 28: hunt a THIRD independent leg -- a submittable factor <0.70
correlated to BOTH the short reversal (A) and the long return-reversal B
(normalize(-ts_rank(returns,220))). normalize() only boosts fitness for
SH>=1.25 signals, so test reversal on DIFFERENT bases (close/vwap/high) and
EXTREME horizons (returns-500) which may decorrelate from B's returns-220.
Correlation to A and B is measured after."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d=22):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    ("normalize(-ts_rank(close, 220))",  cfg(22)),
    ("normalize(-ts_rank(vwap, 220))",   cfg(22)),
    ("normalize(-ts_rank(high, 220))",   cfg(22)),
    ("normalize(-ts_rank(low, 220))",    cfg(22)),
    ("normalize(-ts_rank(returns, 500))", cfg(24)),
    ("normalize(-ts_delta(close, 120))", cfg(16)),
    ("normalize(-ts_rank(vwap, 120))",   cfg(22)),
    ("normalize(-ts_rank(close, 500))",  cfg(24)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch28.json", "w"), indent=2)
print("=== SAVED batch28.json ===")
