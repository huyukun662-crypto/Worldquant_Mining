"""Batch 34: NEW module (fundamental6) + NEW structure (accounting-ratio
value/quality anomalies). Strongest documented fundamental factors:
profitability (ROA), cashflow/EBITDA yield (value), low investment, book/EV.
Orthogonal to reversal. rank() probes sign; slow signals -> fitness floor
helps. Find SH>=1.25 & FIT>=1.0."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d=6):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

cands = [
    ("rank(divide(ebitda, enterprise_value))",            cfg(6)),   # EBITDA/EV value
    ("rank(divide(cashflow_op, enterprise_value))",       cfg(6)),   # cashflow yield
    ("rank(divide(ebit, assets))",                        cfg(6)),   # ROA / profitability
    ("rank(divide(subtract(ebit, capex), assets))",       cfg(6)),   # profit net of capex
    ("-rank(divide(capex, assets))",                      cfg(6)),   # low investment
    ("rank(divide(cashflow_op, assets))",                 cfg(6)),   # cashflow/assets
    ("rank(divide(equity, enterprise_value))",            cfg(6)),   # book/EV value
    ("-rank(divide(debt, equity))",                       cfg(6)),   # low leverage
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch34.json", "w"), indent=2)
print("=== SAVED batch34.json ===")
