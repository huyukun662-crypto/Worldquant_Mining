"""Batch 2: volume-price interaction reversals (stronger than pure price
reversal, which topped out at SH~0.96 in batch1). Target SH>=1.25,
TO<=0.25, fitness>=1.0 on a non-TOP3000 universe."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

cands = [
    # price-volume divergence reversal (classic high-sharpe simple alpha)
    ("-ts_corr(close, volume, 10)",            settings("TOP1000", "SUBINDUSTRY", decay=6)),
    # volume-weighted short-term reversal
    ("multiply(-ts_delta(close, 5), ts_rank(volume, 5))", settings("TOP1000", "SUBINDUSTRY", decay=10)),
    # high-volume reversal of daily return
    ("multiply(-returns, ts_rank(volume, 10))", settings("TOP1000", "SUBINDUSTRY", decay=8)),
    # vwap intraday reversion
    ("divide(subtract(vwap, close), close)",   settings("TOP1000", "SUBINDUSTRY", decay=8)),
    # rank-correlation price/volume divergence
    ("-ts_corr(rank(close), rank(volume), 10)", settings("TOP1000", "SUBINDUSTRY", decay=6)),
    # corr on smaller universe
    ("-ts_corr(close, volume, 10)",            settings("TOP500", "SUBINDUSTRY", decay=6)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch2.json", "w"), indent=2)
print("=== SAVED batch2.json ===")
