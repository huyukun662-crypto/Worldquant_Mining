"""Batch 3: model16 fundamental composite scores. Slow-moving -> very low
turnover -> high fitness, with genuine predictive power. A single rank()
of each tells us the sign (negative SH => use -rank)."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

# decay small; these update slowly already. SUBINDUSTRY neutralization,
# avoid TOP3000 (use TOP1000).
st = lambda u="TOP1000", n="SUBINDUSTRY", d=4: settings(u, n, decay=d)

cands = [
    ("rank(fscore_value)",          st()),
    ("rank(fscore_quality)",        st()),
    ("rank(fscore_total)",          st()),
    ("rank(fscore_profitability)",  st()),
    ("rank(fscore_growth)",         st()),
    ("rank(fscore_momentum)",       st()),
    ("rank(fscore_surface)",        st()),
    ("rank(earnings_certainty_rank_derivative)", st()),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch3.json", "w"), indent=2)
print("=== SAVED batch3.json ===")
