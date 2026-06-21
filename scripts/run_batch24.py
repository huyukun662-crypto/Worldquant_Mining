"""Batch 24: truncation boost on TOPSP500/TOP500 reversal. Best configs cap
at FIT 0.89-0.90 but with big Sharpe headroom (1.73-1.79). Higher truncation
concentrates positions -> higher returns -> higher fitness; SH headroom
should absorb the concentration. Target: clear FIT 1.0 on a non-TOP3000
universe (TOPSP500 = S&P 500)."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

R10 = "rank(-ts_rank(returns, 10))"

def cfg(u, d, t):
    return settings(u, "SUBINDUSTRY", decay=d, trunc=t)

cands = [
    (R10, cfg("TOPSP500", 24, 0.12)),
    (R10, cfg("TOPSP500", 24, 0.15)),
    (R10, cfg("TOPSP500", 24, 0.20)),
    (R10, cfg("TOP500",   24, 0.12)),
    (R10, cfg("TOP500",   24, 0.15)),
    (R10, cfg("TOPSP500", 20, 0.15)),
    (R10, cfg("TOP500",   20, 0.15)),
    (R10, cfg("TOPSP500", 24, 0.10)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch24.json", "w"), indent=2)
print("=== SAVED batch24.json ===")
