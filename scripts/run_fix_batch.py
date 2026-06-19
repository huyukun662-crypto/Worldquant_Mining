"""Fix CONCENTRATED_WEIGHT on the winning fresh news_short_interest factor
(fresh_ey: SH 2.07, FIT 3.27, only CONCENTRATED_WEIGHT fails).

Concentration is capped most directly by lowering `truncation` (hard cap
on per-name weight) and by ts_decay_linear smoothing. Keep SH>=2.0/FIT>=1.3.
"""
from scripts.d0_batch import run_batch

EXPR = ("signed_power(winsorize(add("
        "group_zscore(ts_backfill(news_short_interest, 44), subindustry), "
        "multiply(0.3, zscore(ts_backfill(divide(ebit, enterprise_value), 22)))"
        "), std=4), 0.05)")
EXPR_DL = f"ts_decay_linear({EXPR}, 10)"

C = [
 ("t04",      EXPR,    {"neutralization":"SUBINDUSTRY","truncation":0.04,"decay":0}),
 ("t02",      EXPR,    {"neutralization":"SUBINDUSTRY","truncation":0.02,"decay":0}),
 ("t03_d6",   EXPR,    {"neutralization":"SUBINDUSTRY","truncation":0.03,"decay":6}),
 ("t02_d8",   EXPR,    {"neutralization":"SUBINDUSTRY","truncation":0.02,"decay":8}),
 ("dl_t05",   EXPR_DL, {"neutralization":"SUBINDUSTRY","truncation":0.05,"decay":0}),
 ("dl_t03",   EXPR_DL, {"neutralization":"SUBINDUSTRY","truncation":0.03,"decay":0}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=2)
