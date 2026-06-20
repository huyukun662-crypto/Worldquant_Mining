"""Batch 30: push the two NEW structures from batch29 toward FIT>=1.0.
- ts_zscore(returns,N) reversal (different normalizer than ts_rank): SH 1.31
- vol-scaled / risk-adjusted reversal divide(-ret, ts_std_dev): SH 1.23
Short horizon + decay lifted fitness for the ts_rank family; apply the same
to these new structures. Genuinely different from ts_rank(returns)."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    # zscore reversal, short horizons + decay (analog of winner, diff operator)
    ("normalize(-ts_zscore(returns, 5))",  cfg(16)),
    ("normalize(-ts_zscore(returns, 7))",  cfg(18)),
    ("normalize(-ts_zscore(returns, 10))", cfg(20)),
    ("normalize(-ts_zscore(returns, 5))",  cfg(20)),
    # vol-scaled / risk-adjusted reversal (genuinely different structure)
    ("normalize(divide(-ts_mean(returns, 5), ts_std_dev(returns, 20)))",  cfg(18)),
    ("normalize(divide(-ts_mean(returns, 7), ts_std_dev(returns, 22)))",  cfg(18)),
    ("normalize(divide(-returns, ts_std_dev(returns, 20)))",              cfg(24)),
    ("normalize(divide(-ts_sum(returns, 5), ts_std_dev(returns, 60)))",   cfg(20)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch30.json", "w"), indent=2)
print("=== SAVED batch30.json ===")
