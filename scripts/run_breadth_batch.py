"""Wide persistent-signal composite -> target SH>=2.0 via BREADTH.

Insight from the account's SH=2.08 / TO=0.013 alpha: high Sharpe at near-
zero turnover comes from combining MANY weak-but-persistent, mutually
uncorrelated signals (fundamental law: IR = IC * sqrt(breadth)), each
rank-normalized, then heavily neutralized:
  group_neutralize(., pv13_r2_min5_3000_sector)  # statistical risk model
  group_neutralize(., subindustry)
  vector_neut(., returns)                         # market/beta clean
  hump(., 0.1)                                     # turnover -> ~0

Signals (all persistent -> low turnover, economically grounded, fresh:
no news_short_interest, no IV):
  Fundamental: ebit/ev[+], ebit/assets[+], cfo/assets[+], -asset_growth[-],
               -debt/assets[-]
  Analyst    : coverage[+], -dispersion[+/-], revision[+]
  Slow PV    : -ts_std_dev(returns,120)[+], -ts_av_diff(close,750)[+]
"""
from scripts.d0_batch import run_batch

def Tb(x, bf=120):
    return f"rank(winsorize(ts_backfill({x}, {bf}), std=4))"
def T(x):
    return f"rank(winsorize({x}, std=4))"

value = Tb("divide(ebit, enterprise_value)")
prof  = Tb("divide(ebit, assets)")
cfq   = Tb("divide(cashflow_op, assets)")
inv   = Tb("divide(ts_delta(assets, 250), assets)", 250)
lev   = Tb("divide(debt, assets)")
cov   = Tb("vec_avg(anl4_basicconqf_numest)", 66)
disp  = Tb("divide(subtract(vec_avg(anl4_basicconqf_high), vec_avg(anl4_basicconqf_low)), "
           "add(abs(vec_avg(anl4_basicconqf_mean)), 1))", 66)
rev   = Tb("ts_delta(est_epsr, 60)", 120)         # EPS revision (slow)
lowv  = T("-ts_std_dev(returns, 120)")
ltrev = T("-ts_av_diff(close, 750)")

WIDE = f"{value} + {prof} + {cfq} - {inv} - {lev} + {cov} + {disp} + {rev} + {lowv} + {ltrev}"
RISK = "pv13_r2_min5_3000_sector"

C = [
 # 1) wide composite, risk-model + subindustry neut + vneut + hump
 ("wide_full",
  f"hump(vector_neut(group_neutralize(group_neutralize({WIDE}, {RISK}), subindustry), returns), hump=0.1)",
  {"neutralization":"SUBINDUSTRY","decay":4}),
 # 2) wide, risk-model neut only + vneut + hump
 ("wide_risk",
  f"hump(vector_neut(group_neutralize({WIDE}, {RISK}), returns), hump=0.1)",
  {"neutralization":"SUBINDUSTRY","decay":4}),
 # 3) wide, plain subindustry + vneut + hump (no risk model)
 ("wide_sub",
  f"hump(vector_neut(group_neutralize({WIDE}, subindustry), returns), hump=0.1)",
  {"neutralization":"SUBINDUSTRY","decay":4}),
 # 4) wide, risk-model + subindustry, NO vneut
 ("wide_novneut",
  f"hump(group_neutralize(group_neutralize({WIDE}, {RISK}), subindustry), hump=0.1)",
  {"neutralization":"SUBINDUSTRY","decay":4}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=1)
