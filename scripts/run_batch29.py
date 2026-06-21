"""Batch 29: REPLACE the ts_rank(returns) reversal structure -- mine
genuinely different structures on TOP1000 targeting SH>=1.25 & FIT>=1.0.
normalize() wraps for fitness. Invalid operators surface as ERROR.
Structures: zscore reversal, vol-scaled reversal, skewness premium,
price-volume divergence, decay-linear reversal, av_diff."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d=16):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    # vol-scaled reversal (risk-adjusted) -- different structure
    ("normalize(divide(-returns, ts_std_dev(returns, 20)))",       cfg(16)),
    ("normalize(divide(-ts_delta(close, 5), ts_std_dev(returns, 20)))", cfg(16)),
    # zscore reversal (different normalizer than ts_rank)
    ("normalize(-ts_zscore(returns, 22))",                          cfg(16)),
    # higher-moment: skewness / kurtosis premium
    ("normalize(-ts_skewness(returns, 120))",                       cfg(16)),
    ("normalize(ts_kurtosis(returns, 120))",                        cfg(16)),
    # price-volume divergence over long window
    ("normalize(-ts_corr(close, volume, 120))",                     cfg(16)),
    # smoothed-returns reversal via decay_linear
    ("normalize(-ts_decay_linear(returns, 10))",                    cfg(16)),
    # average-difference reversal
    ("normalize(-ts_av_diff(close, 22))",                           cfg(16)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch29.json", "w"), indent=2)
print("=== SAVED batch29.json ===")
