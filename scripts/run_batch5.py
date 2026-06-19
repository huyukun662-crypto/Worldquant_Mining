"""Batch 5: composites of orthogonal slow signals. Single fields topped out
at SH~0.7; combining uncorrelated low-turnover signals lifts Sharpe while
keeping turnover near the 0.125 fitness floor.

Signs learned from batches 3-4 (rank() sign that yields positive Sharpe):
  + rank(fscore_value)                         +0.68
  - rank(fscore_growth)                        +0.59
  + rank(fscore_quality)                       +0.42
  - rank(composite_factor_score_derivative)    +0.46  (analyst-revision mom)
  - rank(ts_delta(close,5))                    +0.96  (short-term reversal)
"""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

V = "rank(fscore_value)"
Q = "rank(fscore_quality)"
M = "rank(composite_factor_score_derivative)"   # subtract (neg sign)
R = "rank(ts_delta(close, 5))"                   # subtract (reversal)
G = "rank(fscore_growth)"                         # subtract (neg sign)

def sub(a, b): return f"subtract({a}, {b})"
def add(a, b): return f"add({a}, {b})"

c1 = sub(V, M)                       # value + analyst momentum
c2 = sub(add(V, Q), M)               # value + quality + momentum
c3 = sub(sub(V, M), R)               # value + momentum + reversal
c4 = sub(sub(add(V, Q), M), R)       # value + quality + momentum + reversal
c5 = sub(sub(sub(V, M), R), G)       # value + momentum + reversal - growth

st = lambda u="TOP1000", n="SUBINDUSTRY", d=6: settings(u, n, decay=d)

cands = [
    (c1, st()),
    (c2, st()),
    (c3, st()),
    (c4, st()),
    (c5, st()),
    (c3, st("TOP500")),
    (c4, st(d=10)),
    (c4, st(n="MARKET")),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch5.json", "w"), indent=2)
print("=== SAVED batch5.json ===")
