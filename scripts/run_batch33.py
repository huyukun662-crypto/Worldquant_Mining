"""Batch 33: NEW module (analyst4) + NEW structure (estimate-revision
momentum). Leaves price-volume entirely. Earnings-revision is a strong real
anomaly, orthogonal to reversal. rank() probes sign; analyst signals are
slow (low turnover -> fitness floor helps). Find SH>=1.25 & FIT>=1.0."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def cfg(d=6):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

EPS = "anl4_afv4_eps_mean"
RAT = "anl4_basicdetailrec_ratingvalue"

cands = [
    (f"rank(ts_delta({EPS}, 66))",                              cfg(6)),   # quarterly EPS revision
    (f"rank(divide(ts_delta({EPS}, 66), abs({EPS})))",         cfg(6)),   # % EPS revision
    (f"rank(ts_delta({EPS}, 22))",                             cfg(6)),   # monthly EPS revision
    (f"rank(ts_delta({RAT}, 22))",                             cfg(6)),   # rating change
    (f"rank({RAT})",                                           cfg(6)),   # rating level
    (f"rank(divide({EPS}, close))",                            cfg(6)),   # forward earnings yield
    (f"-rank(adj_net_income_stddev)",                          cfg(6)),   # low dispersion premium
    (f"rank(divide(ts_delta({EPS}, 22), anl4_afv4_eps_number))", cfg(6)), # revision per analyst
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch33.json", "w"), indent=2)
print("=== SAVED batch33.json ===")
