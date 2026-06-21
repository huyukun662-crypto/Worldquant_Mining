"""Batch 18: push the corr-0.61 returns-120 reversal over fitness 1.0 via
NEUTRALIZATION and nearby HORIZONS (not yet tried -- earlier sweeps only
touched decay/truncation). NONE/MARKET keep more long-term return (higher
fitness); horizons 90/150/200 may hit a better SH/fitness point while
staying <0.70 correlated with the returns-5 winner."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(n="SUBINDUSTRY", d=16, u="TOP1000"):
    return settings(u, n, decay=d, trunc=0.08)

R = lambda n: f"rank(-ts_rank(returns, {n}))"

cands = [
    (R(120), st("MARKET")),
    (R(120), st("NONE")),
    (R(120), st("INDUSTRY")),
    (R(90),  st("SUBINDUSTRY")),
    (R(150), st("SUBINDUSTRY")),
    (R(200), st("SUBINDUSTRY")),
    (R(120), st("SUBINDUSTRY", d=10)),
    (R(90),  st("MARKET")),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch18.json", "w"), indent=2)
print("=== SAVED batch18.json ===")
