"""Batch 14: reversal TERM-STRUCTURE spreads. short_reversal -
long_reversal removes the common reversal factor -> expected corr ~0.4-0.5
to the pure short-reversal winner (below the 0.70 self-corr limit), while
still a real signal (short reversal stronger than long). If it passes
fitness, it's a genuine low-correlation submittable factor."""
import sys, json
sys.path.insert(0, "scripts")
from d1_miner import run_batch, settings

def st(d=16):
    return settings("TOP1000", "SUBINDUSTRY", decay=d, trunc=0.08)

R = lambda n: f"rank(-ts_rank(returns, {n}))"
M = lambda n: f"rank(ts_rank(returns, {n}))"

cands = [
    (f"subtract({R(5)}, {R(120)})", st(16)),
    (f"subtract({R(5)}, {R(60)})",  st(16)),
    (f"subtract({R(5)}, {R(22)})",  st(16)),
    (f"subtract({R(10)}, {R(120)})", st(16)),
    (f"add({R(5)}, {M(120)})",      st(16)),   # short reversal + long momentum
    (f"subtract({R(5)}, {R(120)})", st(8)),
    (f"subtract({R(5)}, {R(120)})", st(24)),
    (f"subtract({R(3)}, {R(40)})",  st(16)),
]

s, done = run_batch(cands, max_concurrent=4)
json.dump([{k: v for k, v in d.items() if k != "st"} for d in done],
          open("batch14.json", "w"), indent=2)
print("=== SAVED batch14.json ===")
