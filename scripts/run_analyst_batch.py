"""Analyst-data (analyst4) delay-0 candidates: dispersion / revision /
net-optimism / coverage anomalies. Persistent (long backfill) -> low
turnover, distinct economic mechanism from news_short_interest.

All anl4_* are VECTOR fields -> reduce with vec_avg. Regularized with
group_zscore + winsorize + signed_power. No IV, no short_interest.
"""
from scripts.d0_batch import run_batch

N = "SUBINDUSTRY"

# consensus quarterly forecast fields (basicconqf): high/low/mean/numest/down/pu
hi  = "vec_avg(anl4_basicconqf_high)"
lo  = "vec_avg(anl4_basicconqf_low)"
mn  = "vec_avg(anl4_basicconqf_mean)"
nest= "vec_avg(anl4_basicconqf_numest)"
dn  = "vec_avg(anl4_basicconqf_down)"
pu  = "vec_avg(anl4_basicconqf_pu)"

C = [
 # 1) Forecast-DISPERSION anomaly (Diether et al 2002): high disagreement
 #    -> lower future returns. dispersion = (high-low)/|mean|.
 ("disp_short",
  f"-group_zscore(ts_backfill(divide(subtract({hi},{lo}), add(abs({mn}),1)), 66), subindustry)",
  {"neutralization":N,"decay":16}),
 # 2) Same, winsorized+signed_power (strong construction)
 ("disp_strong",
  f"signed_power(winsorize(-1 * group_zscore(ts_backfill(divide(subtract({hi},{lo}), add(abs({mn}),1)), 66), subindustry), std=4), 0.2)",
  {"neutralization":N,"decay":16}),
 # 3) Net-OPTIMISM: (#up - #down)/#est. More upgrades -> drift up.
 ("optim",
  f"group_zscore(ts_backfill(divide(subtract({pu},{dn}), add({nest},1)), 66), subindustry)",
  {"neutralization":N,"decay":16}),
 # 4) Estimate-REVISION drift: mean consensus rising -> positive drift.
 ("revis",
  f"group_zscore(ts_backfill(ts_delta({mn}, 22), 66), subindustry)",
  {"neutralization":N,"decay":16}),
 # 5) Revision normalized by price level (scale-free)
 ("revis_norm",
  f"group_zscore(ts_backfill(divide(ts_delta({mn}, 22), add(abs({mn}),1)), 66), subindustry)",
  {"neutralization":N,"decay":16}),
 # 6) Neglected-firm: low coverage -> higher returns (short high coverage)
 ("coverage",
  f"-group_zscore(ts_backfill({nest}, 66), subindustry)",
  {"neutralization":N,"decay":16}),
 # 7) Dispersion x downgrade interaction, INDUSTRY neut
 ("disp_dn",
  f"-group_zscore(ts_backfill(multiply(divide(subtract({hi},{lo}), add(abs({mn}),1)), add({dn},1)), 66), industry)",
  {"neutralization":"INDUSTRY","decay":16}),
 # 8) Optimism strong construction
 ("optim_strong",
  f"signed_power(winsorize(group_zscore(ts_backfill(divide(subtract({pu},{dn}), add({nest},1)), 66), subindustry), std=4), 0.2)",
  {"neutralization":N,"decay":16}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=3)
