"""Batch 20: push the decorrelated long reversals over BOTH gates.
returns-200 SUBINDUSTRY decay16 = SH 1.59 / FIT 0.96 / TO 0.46 (TO well
above the 0.125 fitness floor, so higher decay cuts TO -> lifts fitness
while SH stays high). returns-120 decay10 had SH 1.68. Sweep decay/horizon
around the 200 sweet spot; INDUSTRY variants too."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(n="SUBINDUSTRY", d=16, t=0.08):
    return settings("TOP1000", n, decay=d, trunc=t)

R = lambda n: f"rank(-ts_rank(returns, {n}))"

cands = [
    (R(200), st("SUBINDUSTRY", 24)),
    (R(200), st("SUBINDUSTRY", 20)),
    (R(200), st("SUBINDUSTRY", 32)),
    (R(250), st("SUBINDUSTRY", 16)),
    (R(250), st("SUBINDUSTRY", 24)),
    (R(180), st("SUBINDUSTRY", 24)),
    (R(200), st("SUBINDUSTRY", 16, t=0.12)),
    (R(200), st("INDUSTRY", 24)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch20.json", "w"), indent=2)
print("=== SAVED batch20.json ===")
