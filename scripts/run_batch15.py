"""Batch 15: vol-matched BLENDS of the reversal winner with an orthogonal
weak signal (fscore_*). Two ~uncorrelated signals diversify: blended
Sharpe ~ (SH_A+SH_B)/sqrt(2), and a ~50/50 weight pulls correlation to the
pure reversal toward 0.70 -- tilting to the orthogonal side drops it below
0.70 while (hopefully) keeping fitness >= 1.0. This is a composite (2-term)
expression -- the route to a genuinely low-correlation submittable factor."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

st = settings("TOP1000", "SUBINDUSTRY", decay=16, trunc=0.08)
REV = "rank(-ts_rank(returns, 5))"

cands = [
    (f"add({REV}, rank(fscore_value))",                  dict(st)),
    (f"add({REV}, rank(fscore_quality))",                dict(st)),
    (f"add({REV}, rank(fscore_total))",                  dict(st)),
    (f"add({REV}, rank(fscore_growth))",                 dict(st)),
    # tilt toward the orthogonal (value) side -> lower correlation
    (f"add({REV}, multiply(2, rank(fscore_value)))",     dict(st)),
    (f"add({REV}, multiply(3, rank(fscore_value)))",     dict(st)),
    # tilt toward reversal -> higher fitness, higher corr
    (f"add(multiply(2, {REV}), rank(fscore_value))",     dict(st)),
    (f"add({REV}, add(rank(fscore_value), rank(fscore_quality)))", dict(st)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch15.json", "w"), indent=2)
print("=== SAVED batch15.json ===")
