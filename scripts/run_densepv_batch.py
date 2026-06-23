"""Fresh DENSE price-volume D0 factors in the submittable archetype.

The account's ONLY submitted D0 alpha (1Y751gZm, SH 2.05, all checks pass)
is a DENSE PV factor with neutralization=NONE and ts_decay_linear smoothing
(Amihud illiquidity over 750d + 5/20-day reversal). Dense PV => the book
spans all names => CONCENTRATED_WEIGHT passes (news_short_interest cannot:
it is sparse and structurally concentrates).

Here we build a FRESH dense PV factor uncorrelated with 1Y751gZm by using
DIFFERENT, economically-grounded signals (avoiding its Amihud + 5/20d
reversal terms):
  * Low-volatility anomaly     : -ts_std_dev(returns, 60)
  * Price-volume divergence    : -ts_corr(close, volume, 20)
  * Intraday close-position rev : -(close-low)/(high-low)   (buying-pressure reversal)
  * Long-horizon reversal       : -ts_av_diff(close, 250)   (DeBondt-Thaler)

Regularized with zscore + ts_decay_linear. neut NONE (proven archetype).
No IV, no short_interest.
"""
from scripts.d0_batch import run_batch

def z(x, dl):
    return f"zscore(ts_decay_linear({x}, {dl}))"

lowv  = z("-ts_std_dev(returns, 60)", 20)
pvcor = z("-ts_corr(close, volume, 20)", 20)
intra = z("-divide(subtract(close, low), add(subtract(high, low), 0.001))", 20)
ltrev = z("-ts_av_diff(close, 250)", 60)

COMP4 = f"add(add({lowv}, {pvcor}), add({intra}, {ltrev}))"
COMP3 = f"add(add({lowv}, {pvcor}), {ltrev})"

C = [
 ("comp4_none",  COMP4, {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("comp3_none",  COMP3, {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("lowv_none",   lowv,  {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("ltrev_none",  ltrev, {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("comp4_mkt",   COMP4, {"neutralization":"MARKET","truncation":0.05,"decay":0}),
 ("comp4_sub",   COMP4, {"neutralization":"SUBINDUSTRY","truncation":0.05,"decay":0}),
 ("pvcor_none",  pvcor, {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("intra_none",  intra, {"neutralization":"NONE","truncation":0.05,"decay":0}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=2)
