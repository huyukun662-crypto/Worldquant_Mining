"""Batch 7: lift fitness on rank(-returns) decay8 (SH 1.53, TO 0.63, FIT
0.86 -- only fitness fails). Fitness = SH*sqrt(|ret|/max(TO,0.125)); raise
returns by concentrating positions via higher truncation. Sweep truncation
(and a couple of neut/universe variants)."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

REV = "rank(-returns)"

def st(trunc, n="SUBINDUSTRY", d=8, u="TOP1000"):
    return settings(u, n, decay=d, trunc=trunc)

cands = [
    (REV, st(0.10)),
    (REV, st(0.15)),
    (REV, st(0.20)),
    (REV, st(0.30)),
    (REV, st(0.15, d=6)),
    (REV, st(0.20, d=6)),
    (REV, st(0.20, n="MARKET")),
    (REV, st(0.20, u="TOP500")),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch7.json", "w"), indent=2)
print("=== SAVED batch7.json ===")
