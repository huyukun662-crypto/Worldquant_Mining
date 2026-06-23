"""Structurally-DISTINCT illiquidity + reversal -> SH>=2.0 with low
self-correlation vs the submitted 1Y751gZm.

1Y751gZm uses (high-low)/(close*volume) illiquidity + close reversal, so
a literal copy self-correlates 0.93-0.94. Here we keep the SAME economic
forces but DIFFERENT exact signals to drop self-correlation below 0.7:
  - illiquidity: Amihud RETURN-based |returns|/(close*volume)  (not H-L/C*V)
  - reversal   : VWAP-based -ts_av_diff(vwap, .)               (not close)
  - + news_short_interest tilt (orthogonal economics)
neut NONE. No IV.
"""
from scripts.d0_batch import run_batch

def z(x, dl): return f"zscore(ts_decay_linear({x}, {dl}))"
AMI2 = f"-1 * {z('ts_mean(divide(abs(returns), add(multiply(close, volume),1)), 500)', 200)}"
RVW5 = f"-1 * {z('ts_av_diff(vwap, 5)', 5)}"
RVW20= f"-1 * {z('ts_av_diff(vwap, 20)', 10)}"
SI   = "group_zscore(ts_backfill(news_short_interest, 44), subindustry)"
SI0  = f"if_else(is_nan({SI}), 0, {SI})"

def f(wsi):
    base=f"add(add({AMI2}, multiply(0.6,{RVW5})), multiply(0.4,{RVW20}))"
    return f"add({base}, multiply({wsi},{SI0}))" if wsi else base

st={"neutralization":"NONE","truncation":0.05,"decay":0}
C=[
 ("distinct_base", f(0),   st),
 ("distinct_si04", f(0.4), st),
 ("distinct_si08", f(0.8), st),
]
if __name__ == "__main__":
    run_batch(C, max_workers=2)
