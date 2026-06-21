"""Batch 6: decay sweep of the 1-day reversal rank(-returns).

Calibration: rank(-returns) decay4 -> SH 1.61, TO 0.84 (fails HIGH_TURNOVER
and fitness). Reversal is by far the strongest signal; the only problem is
turnover. Sweep decay to pull TO under 0.70 while keeping SH high enough
that fitness = SH*sqrt(|ret|/max(TO,0.125)) >= 1.0.

Also a few ts_rank reversal variants (smoother, lower turnover natively)."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

REV = "rank(-returns)"
TSR = "rank(-ts_rank(returns, 5))"   # rank of 5d return rank, reversed

cands = [
    (REV, settings("TOP1000", "SUBINDUSTRY", decay=8)),
    (REV, settings("TOP1000", "SUBINDUSTRY", decay=12)),
    (REV, settings("TOP1000", "SUBINDUSTRY", decay=16)),
    (REV, settings("TOP1000", "SUBINDUSTRY", decay=24)),
    (REV, settings("TOP1000", "SUBINDUSTRY", decay=32)),
    (TSR, settings("TOP1000", "SUBINDUSTRY", decay=8)),
    (TSR, settings("TOP1000", "SUBINDUSTRY", decay=16)),
    (REV, settings("TOP500",  "SUBINDUSTRY", decay=16)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch6.json", "w"), indent=2)
print("=== SAVED batch6.json ===")
