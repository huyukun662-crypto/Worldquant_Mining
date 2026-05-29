"""Round-2 D0 candidates: refine the round-1 leads toward SH>1.25, TO<0.25.

Round-1 findings (delay=0, TOP3000):
  retvol_cov_fade         -zscore(ts_covariance(returns,volume,20))  SH .80 TO .13 FIT 1.15
  cond_reversal_tradewhen trade_when(vol up, -group_zscore(ts_av_diff(close,5),ind),-1)  SH .92 TO .32
  concave (flip)          -zscore(signed_power(ts_delta(vwap,10),0.5))  SH ~.82 TO .26
The covariance-fade signal has excellent turnover (.13) and fitness (1.15);
its only failing gate is Sharpe. Smaller universes + decay tuning + combining
with an uncorrelated price-reversal signal are the levers to clear 1.25.
All operators are tier-available; still D0, regularized, niche, no IV.
"""

CANDIDATES = [
    # --- covariance-fade across smaller universes (Sharpe lever) ---
    {
        "name": "cov_fade_top1000",
        "expression": "-zscore(ts_covariance(returns, volume, 20))",
        "theme": "Return-volume covariance fade on TOP1000 (cleaner names).",
        "settings": {"universe": "TOP1000", "decay": 8, "neutralization": "SUBINDUSTRY"},
    },
    {
        "name": "cov_fade_top500",
        "expression": "-zscore(ts_covariance(returns, volume, 20))",
        "theme": "Return-volume covariance fade on TOP500.",
        "settings": {"universe": "TOP500", "decay": 8, "neutralization": "SUBINDUSTRY"},
    },
    {
        "name": "cov_fade_top1000_ind16",
        "expression": "-zscore(ts_covariance(returns, volume, 20))",
        "theme": "Covariance fade, INDUSTRY-neutral, heavier decay to denoise.",
        "settings": {"universe": "TOP1000", "decay": 16, "neutralization": "INDUSTRY"},
    },
    {
        "name": "cov_fade_w40_top1000",
        "expression": "-zscore(ts_covariance(returns, volume, 40))",
        "theme": "Covariance fade, longer 40d window, TOP1000.",
        "settings": {"universe": "TOP1000", "decay": 8, "neutralization": "SUBINDUSTRY"},
    },
    {
        "name": "cov_fade_sp_top1000",
        "expression": "-zscore(signed_power(ts_covariance(returns, volume, 20), 0.5))",
        "theme": "Covariance fade sharpened by signed sqrt (tames tails), TOP1000.",
        "settings": {"universe": "TOP1000", "decay": 8, "neutralization": "SUBINDUSTRY"},
    },
    # --- composites: covariance (volume source) + price-reversal source ---
    {
        "name": "combo_cov_vwaprev_top1000",
        "expression": "-zscore(ts_covariance(returns, volume, 20)) - zscore(signed_power(ts_delta(vwap, 10), 0.5))",
        "theme": "Diversified fade: volume-confirmed move fade + outlier-tamed "
                 "vwap-move fade (two low-correlation reversal sources).",
        "settings": {"universe": "TOP1000", "decay": 8, "neutralization": "SUBINDUSTRY"},
    },
    {
        "name": "combo_cov_avdiff_top1000",
        "expression": "-zscore(ts_covariance(returns, volume, 20)) - group_zscore(ts_av_diff(close, 5), industry)",
        "theme": "Covariance fade + industry-relative short-term reversal.",
        "settings": {"universe": "TOP1000", "decay": 12, "neutralization": "INDUSTRY"},
    },
    {
        "name": "combo_cov_avdiff_top3000",
        "expression": "-zscore(ts_covariance(returns, volume, 20)) - group_zscore(ts_av_diff(close, 5), industry)",
        "theme": "Same composite on the full TOP3000 universe.",
        "settings": {"universe": "TOP3000", "decay": 12, "neutralization": "INDUSTRY"},
    },
    # --- conditional reversal with heavier decay to pull TO under 0.25 ---
    {
        "name": "cond_reversal_decay20_top1000",
        "expression": "trade_when(ts_delta(volume, 1) > 0, -group_zscore(ts_av_diff(close, 5), industry), -1)",
        "theme": "Conditional industry-relative reversal, decay=20 to cut turnover.",
        "settings": {"universe": "TOP1000", "decay": 20, "neutralization": "SUBINDUSTRY"},
    },
]
