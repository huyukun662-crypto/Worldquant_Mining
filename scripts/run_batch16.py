"""Batch 16: z-score-normalized, REVERSAL-HEAVY blends. rank()-sum blends
collapsed (slow fscore swamps the fast reversal). zscore() puts both on
unit variance so an explicit weight is meaningful; weighting reversal 2-4x
keeps Sharpe/fitness high while a small orthogonal (fscore/low-vol)
component drops correlation to the pure reversal below 0.70."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

st = settings("TOP1000", "SUBINDUSTRY", decay=16, trunc=0.08)
Z = "zscore(-ts_rank(returns, 5))"

def expr(wrev, orth):
    rev = Z if wrev == 1 else f"multiply({wrev}, {Z})"
    return f"add({rev}, zscore({orth}))"

cands = [
    (expr(1, "fscore_value"),    dict(st)),
    (expr(2, "fscore_value"),    dict(st)),
    (expr(3, "fscore_value"),    dict(st)),
    (expr(4, "fscore_value"),    dict(st)),
    (expr(2, "fscore_quality"),  dict(st)),
    (expr(3, "fscore_quality"),  dict(st)),
    (expr(3, "fscore_growth"),   dict(st)),
    (expr(2, "unsystematic_risk_last_360_days"), dict(st)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch16.json", "w"), indent=2)
print("=== SAVED batch16.json ===")
