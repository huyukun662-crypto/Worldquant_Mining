"""Fresh short-interest D0 factor (DIFFERENT field + construction than the
account's existing `news_short_interest` alphas).

Economics: informed short sellers. A high short-interest ratio (shares
shorted / volume = days-to-cover) signals informed bearish conviction and
predicts LOW future returns (Boehmer-Jones-Zhang 2008; Asquith-Pathak-
Ritter 2005). Factor = SHORT the high-short-interest names.

Freshness vs existing book: existing alphas use raw `news_short_interest`
inside `signed_power(winsorize(add(group_zscore(...), sales/cap)))`. Here
we use SIBLING fields (shorted_shares_count_all / short_position_count /
shares_sold_short) and a clean single-term `-group_zscore(ts_backfill(.))`
construction + winsorize regularization. Concise. No IV.
"""
from scripts.d0_batch import run_batch

N = "SUBINDUSTRY"

def si(field, sign="-", bf=66, g="subindustry", wins=False):
    base = f"group_zscore(ts_backfill(vec_avg({field}), {bf}), {g})"
    if wins:
        base = f"winsorize({base}, std=4)"
    return f"{sign}{base}"

C = [
 # sibling short-interest fields, short high-SI, subindustry-neutral
 ("ssc_all",  si("shorted_shares_count_all"),       {"neutralization":N,"decay":8}),
 ("spc",      si("short_position_count"),           {"neutralization":N,"decay":8}),
 ("sss",      si("shares_sold_short"),              {"neutralization":N,"decay":8}),
 ("sssc",     si("shares_sold_short_count"),        {"neutralization":N,"decay":8}),
 ("nws_main", si("nws12_mainz_short_interest"),     {"neutralization":N,"decay":8}),
 # winsorized (regularized) variant of the best-known ratio
 ("ssc_wins", si("shorted_shares_count_all", wins=True), {"neutralization":N,"decay":8}),
 # INDUSTRY-neutral variant
 ("ssc_ind",  si("shorted_shares_count_all", g="industry"), {"neutralization":"INDUSTRY","decay":8}),
 # longer decay smoothing
 ("ssc_d16",  si("shorted_shares_count_all"),       {"neutralization":N,"decay":16}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=2)
