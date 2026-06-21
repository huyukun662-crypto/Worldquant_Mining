"""Batch 35: genuinely different OPERATOR structures (not ts_rank/ts_zscore
on returns). ts_arg_max/min (recency of extremes / crowding), return
autocorrelation, group reversal, av_diff, decay_exp, cumulative-sum
reversal. Invalid operators surface as ERROR. normalize-wrapped."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d=8):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    ("rank(ts_arg_max(close, 22))",                            cfg(8)),   # days since 22d high
    ("rank(ts_arg_min(close, 22))",                            cfg(8)),   # days since 22d low
    ("normalize(-ts_corr(returns, ts_delay(returns, 1), 22))", cfg(8)),   # return autocorrelation
    ("normalize(-ts_av_diff(returns, 5))",                     cfg(8)),   # av_diff reversal
    ("normalize(-ts_sum(returns, 3))",                         cfg(16)),  # 3d cumulative reversal
    ("normalize(-ts_decay_exp_window(returns, 10, factor=0.5))", cfg(8)), # exp-decayed reversal
    ("group_rank(-returns, subindustry)",                      cfg(8)),   # group reversal
    ("rank(-ts_delta(ts_arg_max(close, 22), 5))",              cfg(8)),   # change in high-recency
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch35.json", "w"), indent=2)
print("=== SAVED batch35.json ===")
