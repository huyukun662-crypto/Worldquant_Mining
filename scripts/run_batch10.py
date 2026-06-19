"""Batch 10: NON-reversal families orthogonal to short-term reversal.
Reversal-horizon variants are mutually correlated (0.71-0.92), so a truly
low-correlation submittable factor must come from a different family:
long-horizon momentum, low-volatility / low-beta, liquidity. rank() probes
sign; decay tuned per family."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(d=8, n="SUBINDUSTRY", u="TOP1000", t=0.08):
    return settings(u, n, decay=d, trunc=t)

cands = [
    ("rank(ts_delta(close, 120))",                 st(8)),   # 6m momentum
    ("rank(ts_rank(returns, 250))",                st(8)),   # 12m momentum
    ("rank(ts_delta(close, 230))",                 st(8)),   # ~12m momentum
    ("rank(-unsystematic_risk_last_360_days)",     st(8)),   # low idio-vol
    ("rank(-beta_last_360_days_spy)",              st(8)),   # low beta
    ("rank(-ts_std_dev(returns, 60))",             st(8)),   # low realized vol
    ("rank(-ts_corr(close, volume, 60))",          st(8)),   # long px-vol divergence
    ("rank(ts_delta(vwap, 120))",                  st(8)),   # 6m vwap momentum
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch10.json", "w"), indent=2)
print("=== SAVED batch10.json ===")
