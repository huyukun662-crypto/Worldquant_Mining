"""Batch 12: hunt a genuinely independent (<0.70 corr) submittable factor.
- longer reversal horizons (60, 120): lower corr to returns-5 than 22 (0.71)
- returns-22 under alt neutralization/truncation to cross fitness 1.0
- risk-adjusted / acceleration reversal: different PnL profile"""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(n="SUBINDUSTRY", u="TOP1000", d=16, t=0.08):
    return settings(u, n, decay=d, trunc=t)

cands = [
    ("rank(-ts_rank(returns, 60))",  st(d=16)),                 # quarterly reversal
    ("rank(-ts_rank(returns, 120))", st(d=16)),                 # semiannual reversal
    ("rank(-ts_rank(returns, 60))",  st(d=8)),
    ("rank(-ts_rank(returns, 22))",  st("INDUSTRY", d=16)),
    ("rank(-ts_rank(returns, 22))",  st(d=16, t=0.15)),
    ("rank(divide(-ts_rank(returns, 5), ts_std_dev(returns, 20)))", st(d=16)),
    ("rank(-ts_delta(ts_rank(returns, 5), 5))", st(d=16)),
    ("rank(-ts_rank(returns, 40))",  st(d=16)),                 # 2-month reversal
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch12.json", "w"), indent=2)
print("=== SAVED batch12.json ===")
