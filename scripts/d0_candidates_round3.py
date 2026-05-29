"""Round-3 D0 candidates: push Sharpe to the D0 bar (LOW_SHARPE limit = 2.0).

The live is.checks limits (read off round-2) are the real D0 gates:
    LOW_SHARPE   limit 2.0     (NOT 1.25 -- D0 is far stricter)
    LOW_FITNESS  limit 1.3
    HIGH_TURNOVER limit 0.7    (NOT 0.25 -- lots of turnover headroom)
    LOW_SUB_UNIVERSE_SHARPE ~0.6 ; SELF_CORRELATION < 0.7
Round-2 best: combo_cov_avdiff_top3000 (S1+S2) = SH 1.43, FIT 1.34, TO 0.247,
self-corr 0.53 -- only LOW_SHARPE failing. Two levers: (a) lower decay (we have
turnover room up to 0.7), (b) stack more *uncorrelated* reversal/crowding-fade
sources. All operators tier-available; D0; regularized (per-term zscore);
niche; no IV; no template reuse.

Diverse correct-signed sources (each a fade / reversal from a different place):
    S1 -zscore(ts_covariance(returns, volume, 20))     volume-return crowding
    S2 -group_zscore(ts_av_diff(close, 5), industry)   industry-relative reversal
    S3 -zscore(signed_power(ts_delta(vwap, 10), 0.5))  tamed vwap-move fade
    S4 -zscore(divide(close, open))                     intraday overreaction
    S5 -zscore(divide(open, ts_delay(close, 1)))        overnight gap reversal
"""

S1 = "-zscore(ts_covariance(returns, volume, 20))"
S2 = "-group_zscore(ts_av_diff(close, 5), industry)"
S2f = "-group_zscore(ts_av_diff(close, 3), industry)"
S3 = "-zscore(signed_power(ts_delta(vwap, 10), 0.5))"
S4 = "-zscore(divide(close, open))"
S5 = "-zscore(divide(open, ts_delay(close, 1)))"


CANDIDATES = [
    {"name": "combo2_d4", "expression": f"{S1} - group_zscore(ts_av_diff(close, 5), industry)",
     "theme": "S1+S2, decay 4 (faster than round-2's decay 12).",
     "settings": {"universe": "TOP3000", "decay": 4, "neutralization": "INDUSTRY"}},

    {"name": "triple_d4", "expression": f"{S1} - group_zscore(ts_av_diff(close, 5), industry) - zscore(signed_power(ts_delta(vwap, 10), 0.5))",
     "theme": "S1+S2+S3 (volume + industry-rel + vwap fade), decay 4.",
     "settings": {"universe": "TOP3000", "decay": 4, "neutralization": "INDUSTRY"}},

    {"name": "triple_d2", "expression": f"{S1} - group_zscore(ts_av_diff(close, 5), industry) - zscore(signed_power(ts_delta(vwap, 10), 0.5))",
     "theme": "S1+S2+S3, decay 2.",
     "settings": {"universe": "TOP3000", "decay": 2, "neutralization": "INDUSTRY"}},

    {"name": "triple_d0", "expression": f"{S1} - group_zscore(ts_av_diff(close, 5), industry) - zscore(signed_power(ts_delta(vwap, 10), 0.5))",
     "theme": "S1+S2+S3, decay 0 (max speed).",
     "settings": {"universe": "TOP3000", "decay": 0, "neutralization": "INDUSTRY"}},

    {"name": "quad_d4", "expression": f"{S1} - group_zscore(ts_av_diff(close, 5), industry) - zscore(signed_power(ts_delta(vwap, 10), 0.5)) - zscore(divide(close, open))",
     "theme": "S1+S2+S3+S4 (adds intraday overreaction), decay 4.",
     "settings": {"universe": "TOP3000", "decay": 4, "neutralization": "INDUSTRY"}},

    {"name": "quad_d2", "expression": f"{S1} - group_zscore(ts_av_diff(close, 5), industry) - zscore(signed_power(ts_delta(vwap, 10), 0.5)) - zscore(divide(close, open))",
     "theme": "S1+S2+S3+S4, decay 2.",
     "settings": {"universe": "TOP3000", "decay": 2, "neutralization": "INDUSTRY"}},

    {"name": "quint_d2", "expression": f"{S1} - group_zscore(ts_av_diff(close, 5), industry) - zscore(signed_power(ts_delta(vwap, 10), 0.5)) - zscore(divide(close, open)) - zscore(divide(open, ts_delay(close, 1)))",
     "theme": "S1+S2+S3+S4+S5 (adds overnight gap), decay 2.",
     "settings": {"universe": "TOP3000", "decay": 2, "neutralization": "INDUSTRY"}},

    {"name": "quad_fast_d2", "expression": f"{S1} - group_zscore(ts_av_diff(close, 3), industry) - zscore(signed_power(ts_delta(vwap, 5), 0.5)) - zscore(divide(close, open))",
     "theme": "Faster windows (av_diff 3, vwap delta 5) + intraday, decay 2.",
     "settings": {"universe": "TOP3000", "decay": 2, "neutralization": "INDUSTRY"}},
]
