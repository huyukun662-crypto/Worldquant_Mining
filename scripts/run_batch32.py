"""Batch 32: another NEW structure, avoiding returns-reversal (no
ts_rank/ts_zscore on raw returns). Try structurally different forms:
- liquidity/size-scaled (Amihud-style) reversal: returns/volume, returns/cap
- deviation-from-moving-average (Bollinger): close/ts_mean(close)
- close/vwap, dollar-volume reversal
normalize-wrapped for fitness. Find SH>=1.25 & FIT>=1.0."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d=18):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    ("normalize(-ts_rank(divide(returns, volume), 6))",              cfg(18)),  # Amihud reversal
    ("normalize(-ts_rank(divide(returns, cap), 6))",                 cfg(18)),  # size-scaled
    ("normalize(-ts_rank(multiply(returns, volume), 6))",            cfg(18)),  # dollar-return
    ("normalize(-ts_rank(divide(close, vwap), 6))",                  cfg(18)),  # close/vwap
    ("normalize(-ts_rank(divide(close, ts_mean(close, 20)), 6))",    cfg(18)),  # Bollinger dev
    ("normalize(-ts_delta(divide(close, ts_mean(close, 20)), 5))",   cfg(18)),  # MA-dev change
    ("normalize(-ts_rank(divide(subtract(close, vwap), vwap), 6))",  cfg(18)),  # intraday reversal
    ("normalize(-ts_rank(divide(returns, adv20), 6))",               cfg(18)),  # adv-scaled reversal
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch32.json", "w"), indent=2)
print("=== SAVED batch32.json ===")
