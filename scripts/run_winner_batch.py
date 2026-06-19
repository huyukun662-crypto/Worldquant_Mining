"""Final: Amihud-500 illiquidity + reversal + short-interest tilt.

Goal: a D0 factor passing ALL submit checks incl SELF_CORRELATION < 0.7.
- Amihud illiquidity (H-L)/(C*V) over 500d  -> dense base (CW passes)
- short reversal (5d, 20d)                   -> boosts SH to ~2.0
- news_short_interest tilt (NaN-safe)        -> DIFFERENTIATES from the
  submitted 1Y751gZm (pure illiquidity+reversal, self-corr 0.94) to push
  SELF_CORRELATION below 0.7.

neut NONE. Economic story: illiquidity premium + short-term reversal +
informed short-seller conviction. No IV.
"""
from scripts.d0_batch import run_batch

ILQ = "divide(subtract(high, low), add(multiply(close, volume), 1))"
def z(x, dl): return f"zscore(ts_decay_linear({x}, {dl}))"
AMI  = f"-1 * {z(f'ts_mean({ILQ}, 500)', 200)}"
REV5 = f"-1 * {z('ts_av_diff(close, 5)', 5)}"
REV20= f"-1 * {z('ts_av_diff(close, 20)', 10)}"
SI   = "group_zscore(ts_backfill(news_short_interest, 44), subindustry)"
SI0  = f"if_else(is_nan({SI}), 0, {SI})"

def f(wr5, wr20, wsi):
    return (f"add(add(add({AMI}, multiply({wr5},{REV5})), multiply({wr20},{REV20})), "
            f"multiply({wsi},{SI0}))")

st = {"neutralization":"NONE","truncation":0.05,"decay":0}
C = [
 ("rev_si04", f(0.6, 0.4, 0.4), st),
 ("rev_si06", f(0.6, 0.4, 0.6), st),
 ("rev_si10", f(0.5, 0.3, 1.0), st),
 ("rev_si15", f(0.4, 0.3, 1.5), st),
]

if __name__ == "__main__":
    run_batch(C, max_workers=2)
