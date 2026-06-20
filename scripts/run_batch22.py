"""Batch 22: change direction -> mine on NON-TOP3000 universes. Discover
which universes this account accepts AND test the reversal recipe on each
(a different universe -> different stock set -> naturally low correlation
to the TOP1000 winner). Invalid universes surface as submit errors.
Smaller universes hurt the short-reversal fitness (TOP500 FIT~0.74 at
decay16), so also re-tune decay per universe."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

R = lambda n: f"rank(-ts_rank(returns, {n}))"

cands = [
    (R(5),  settings("TOP500",     "SUBINDUSTRY", decay=16)),
    (R(5),  settings("TOP500",     "SUBINDUSTRY", decay=8)),
    (R(5),  settings("TOP200",     "SUBINDUSTRY", decay=16)),
    (R(5),  settings("TOP200",     "SUBINDUSTRY", decay=8)),
    (R(5),  settings("TOPSP500",   "SUBINDUSTRY", decay=16)),
    (R(5),  settings("TOPDIV3000", "SUBINDUSTRY", decay=16)),
    (R(10), settings("TOP500",     "SUBINDUSTRY", decay=16)),
    (R(5),  settings("MINVOL1M",   "SUBINDUSTRY", decay=16)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch22.json", "w"), indent=2)
print("=== SAVED batch22.json ===")
