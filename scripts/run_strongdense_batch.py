"""Strong DENSE PV D0 factors -> target SH>=2.0 AND pass CONCENTRATED_WEIGHT.

The submittable archetype is dense PV + neut NONE + ts_decay_linear (cf.
1Y751gZm SH 2.05). Short-term REVERSAL is the strongest dense D0 signal.
We build reversal-centric factors (different horizons + volume confirmation
+ a short-window illiquidity term) to reach 2.0, kept distinct from
1Y751gZm (which is Amihud-750d dominated). Verified uncorrelated later via
/check self-correlation (1Y751gZm is submitted, so it is in that check).

No IV, no short_interest.
"""
from scripts.d0_batch import run_batch

def z(x, dl): return f"zscore(ts_decay_linear({x}, {dl}))"

rev3   = z("-ts_av_diff(close, 3)", 5)
rev10  = z("-ts_av_diff(close, 10)", 10)
revvol = z("-multiply(ts_av_diff(close, 5), ts_rank(volume, 20))", 10)   # volume-confirmed reversal
vwaprev= z("-ts_av_diff(divide(vwap, close), 10)", 10)
illiq60= z("ts_mean(divide(abs(ts_av_diff(close,1)), add(multiply(close, volume),1)), 60)", 20)

C = [
 ("revvol_none", revvol, {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("rev10_none",  rev10,  {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("rev3_none",   rev3,   {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("vwaprev_none",vwaprev,{"neutralization":"NONE","truncation":0.05,"decay":0}),
 # composites of reversal + volume + illiquidity
 ("rv_illiq",    f"add(add({revvol}, {rev10}), {illiq60})",
   {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("rv_vwap",     f"add(add({revvol}, {vwaprev}), {rev10})",
   {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("rv_illiq_sub",f"add(add({revvol}, {rev10}), {illiq60})",
   {"neutralization":"SUBINDUSTRY","truncation":0.05,"decay":0}),
 ("revvol_mkt",  revvol, {"neutralization":"MARKET","truncation":0.05,"decay":0}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=2)
