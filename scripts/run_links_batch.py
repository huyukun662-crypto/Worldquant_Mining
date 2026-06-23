"""Economic-links momentum (rel_ret_*) + EPS-revision drift D0 candidates.

Economic story:
  * rel_ret_cust/part/comp = averaged 1-day return of a stock's customers /
    partners / competitors. Information diffuses slowly across economically
    linked firms (Cohen-Frazzini 2008 customer momentum; Menzly-Ozbas 2010
    supply-chain). A stock drifts TOWARD its customers'/partners' returns
    and AWAY from competitors'. Persistent, distinct from short-interest.
  * est_epsr = consensus GAAP EPS estimate. ts_delta = analyst revision ->
    post-revision drift (Stickel/Womack).

All MATRIX fields. Regularized with group_zscore + winsorize + signed_power.
No IV, no news_short_interest.
"""
from scripts.d0_batch import run_batch

N = "SUBINDUSTRY"
LINK = "add(rel_ret_cust, subtract(rel_ret_part, rel_ret_comp))"

C = [
 # 1) pure customer momentum, smoothed
 ("cust_mom",  f"group_zscore(ts_mean(rel_ret_cust, 10), subindustry)",
  {"neutralization":N,"decay":8}),
 # 2) full economic-links spillover (cust + part - comp), smoothed
 ("link_mom",  f"group_zscore(ts_mean({LINK}, 10), subindustry)",
  {"neutralization":N,"decay":8}),
 # 3) link with linear decay weighting (recent peers matter more)
 ("link_decay",f"group_zscore(ts_decay_linear({LINK}, 15), subindustry)",
  {"neutralization":N,"decay":4}),
 # 4) link, strong construction (winsorize + signed_power tail compression)
 ("link_strong",
  f"signed_power(winsorize(group_zscore(ts_mean({LINK}, 10), subindustry), std=4), 0.5)",
  {"neutralization":N,"decay":8}),
 # 5) EPS estimate-revision drift
 ("eps_rev",   f"group_zscore(ts_delta(est_epsr, 60), subindustry)",
  {"neutralization":N,"decay":16}),
 # 6) EPS revision normalized by level (scale-free)
 ("eps_norm",  f"group_zscore(divide(ts_delta(est_epsr, 60), add(abs(est_epsr),1)), subindustry)",
  {"neutralization":N,"decay":16}),
 # 7) composite: links momentum + EPS revision (rank-sum, both winsorized)
 ("link_eps",
  f"winsorize(group_zscore(ts_mean({LINK}, 10), subindustry), std=4) + "
  f"winsorize(group_zscore(ts_delta(est_epsr, 60), subindustry), std=4)",
  {"neutralization":N,"decay":8}),
 # 8) links momentum, INDUSTRY neutralization, longer smoothing
 ("link_ind",  f"group_zscore(ts_mean({LINK}, 20), industry)",
  {"neutralization":"INDUSTRY","decay":8}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=3)
