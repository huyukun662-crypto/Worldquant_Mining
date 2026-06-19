"""news_short_interest D0 factor: proven backbone + FRESH variants.

The account's GOOD (SH~2.0) D0 alphas use `news_short_interest`. We are
authorized to use it. To stay submit-passing AND fresh, we test:
  A) proven baseline (confirm ~2.0 reachable now),
  B-D) fresh variants: different secondary value term, window,
       neutralization, and a short-interest CHANGE/momentum construction.

Economics: news-based short interest = informed short-seller conviction.
Combined with a cheap-value tilt. Regularized (group_zscore/winsorize/
signed_power). Concise, single primary dataset. No IV.
"""
from scripts.d0_batch import run_batch

def nsi(field="news_short_interest", bf=66, g="industry"):
    return f"group_zscore(ts_backfill({field}, {bf}), {g})"

def val(num, den, bf=22):
    return f"zscore(ts_backfill(divide({num}, {den}), {bf}))"

C = [
 # A) proven baseline -- confirm 2.0 is reachable on this account/period
 ("baseline",
  f"signed_power(winsorize(add({nsi()}, multiply(0.25, {val('sales','cap')})), std=4), 0.05)",
  {"neutralization":"INDUSTRY","decay":0}),
 # B) FRESH: value term = earnings yield (ebit/ev), subindustry neut, win 44
 ("fresh_ey",
  f"signed_power(winsorize(add({nsi(bf=44, g='subindustry')}, multiply(0.3, {val('ebit','enterprise_value')})), std=4), 0.05)",
  {"neutralization":"SUBINDUSTRY","decay":0}),
 # C) FRESH: short interest alone, clean single-term, subindustry
 ("fresh_solo",
  f"signed_power(winsorize({nsi(bf=44, g='subindustry')}, std=4), 0.05)",
  {"neutralization":"SUBINDUSTRY","decay":0}),
 # D) FRESH: short-interest CHANGE (momentum of conviction), distinct signal
 ("fresh_chg",
  f"signed_power(winsorize(group_zscore(ts_backfill(ts_delta(news_short_interest, 22), 66), subindustry), std=4), 0.05)",
  {"neutralization":"SUBINDUSTRY","decay":0}),
 # E) FRESH: value term = cashflow yield (cfo/cap), industry neut, win 88
 ("fresh_cfy",
  f"signed_power(winsorize(add({nsi(bf=88)}, multiply(0.3, {val('cashflow_op','cap')})), std=4), 0.05)",
  {"neutralization":"INDUSTRY","decay":0}),
 # F) FRESH: hump for ultra-low turnover, ebit/ev tilt
 ("fresh_hump",
  f"hump(signed_power(winsorize(add({nsi(bf=44, g='subindustry')}, multiply(0.3, {val('ebit','enterprise_value')})), std=4), 0.05), hump=0.01)",
  {"neutralization":"SUBINDUSTRY","decay":0}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=2)
