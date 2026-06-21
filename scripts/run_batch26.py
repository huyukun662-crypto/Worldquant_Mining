"""Batch 26: FRESH operators to break the decorrelated long-reversal's
fitness ceiling (returns-250 = corr 0.51 / FIT 0.98). Not tried before:
- vector_neut(short, long)/(long, short): explicit orthogonalization
- winsorize / scale / zscore wrappers (vs plain rank)
- ts_zscore / ts_mean long-horizon reversion (different long signal)
Goal: a factor that is <0.70 correlated with the winner AND FIT>=1.0."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d=24):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

R5  = "-ts_rank(returns, 5)"
R250 = "-ts_rank(returns, 250)"

cands = [
    # long reversal, alt normalization wrappers (vs rank)
    (f"winsorize(zscore(-ts_rank(returns, 250)), std=4)", cfg(24)),
    (f"scale(-ts_rank(returns, 250))",                    cfg(24)),
    (f"normalize(-ts_rank(returns, 250))",                cfg(24)),
    # explicit orthogonalization of long reversal vs the winner
    (f"rank(vector_neut(rank({R250}), rank({R5})))",      cfg(24)),
    # different long-horizon signals
    (f"rank(-ts_zscore(returns, 250))",                   cfg(24)),
    (f"rank(-ts_mean(returns, 250))",                     cfg(24)),
    (f"rank(-ts_zscore(close, 250))",                     cfg(24)),
    (f"rank(ts_rank(returns, 250))",                      cfg(24)),  # long momentum sign check
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch26.json", "w"), indent=2)
print("=== SAVED batch26.json ===")
