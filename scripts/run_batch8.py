"""Batch 8: diversify the passing recipe (ts_rank-normalized reversal,
decay16, TOP1000, SUBINDUSTRY) across different base fields and horizons,
to find ADDITIONAL submittable factors that are LOW-correlated with the
returns-5 reversal winner. rank() probes the sign."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

st = settings("TOP1000", "SUBINDUSTRY", decay=16, trunc=0.08)

cands = [
    ("rank(-ts_rank(close, 5))",    dict(st)),   # price-level reversal
    ("rank(-ts_rank(vwap, 5))",     dict(st)),   # vwap reversal
    ("rank(-ts_rank(returns, 10))", dict(st)),   # longer return reversal
    ("rank(-ts_rank(returns, 22))", dict(st)),   # monthly reversal
    ("rank(-ts_rank(high, 5))",     dict(st)),   # high reversal
    ("rank(ts_rank(volume, 5))",    dict(st)),   # volume (sign unknown)
    ("rank(-ts_delta(close, 22))",  dict(st)),   # 22d price-change reversal
    ("rank(-ts_rank(vwap, 22))",    dict(st)),   # longer vwap reversal
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch8.json", "w"), indent=2)
print("=== SAVED batch8.json ===")
