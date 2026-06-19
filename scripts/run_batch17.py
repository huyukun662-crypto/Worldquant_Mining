"""Batch 17: FRESH orthogonal families not tried before -- social sentiment
(socialmedia12, cov 1.0) and options-implied vol/skew (option8, cov ~0.97).
These are orthogonal to price reversal by construction, so any passer is
almost certainly <0.70 correlated with the reversal winner. rank() probes
sign; decay light (these are slow-ish)."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(d=4):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    ("rank(scl12_sentiment)",                          st(4)),
    ("rank(snt_value)",                                st(4)),
    ("rank(ts_delta(scl12_sentiment, 22))",            st(4)),
    ("rank(snt_buzz_ret)",                             st(4)),
    ("rank(implied_volatility_mean_skew_30)",          st(4)),
    ("rank(subtract(implied_volatility_call_30, historical_volatility_30))", st(4)),
    ("rank(ts_delta(implied_volatility_call_30, 22))", st(4)),
    ("rank(snt_value_fast_d1)",                        st(4)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch17.json", "w"), indent=2)
print("=== SAVED batch17.json ===")
