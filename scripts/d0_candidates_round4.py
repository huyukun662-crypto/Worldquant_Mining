"""Round-4 D0 candidates: climb from SH 1.43 toward the D0 bar (>=2.0).

Round-3 lesson: LOWER decay hurt (combo2 d4 -> SH 1.33, d12 -> 1.43, and it
also pushed self-corr up to 0.68). So decay ~12 denoises; the real lever is a
better *combination* at a good decay, not speed. Round-4 sweeps decay UP and
neutralization, tests the triple at the good decay, and weights the high-
fitness covariance-fade term more heavily. TOP3000, no IV, niche ops.
"""

S1 = "-zscore(ts_covariance(returns, volume, 20))"
S2 = "-group_zscore(ts_av_diff(close, 5), industry)"
S3 = "-zscore(signed_power(ts_delta(vwap, 10), 0.5))"
S4 = "-zscore(divide(close, open))"
COMBO2 = f"{S1} - group_zscore(ts_av_diff(close, 5), industry)"
TRIPLE = f"{COMBO2} - zscore(signed_power(ts_delta(vwap, 10), 0.5))"

CANDIDATES = [
    {"name": "combo2_d8", "expression": COMBO2,
     "theme": "Best combo, decay 8.",
     "settings": {"universe": "TOP3000", "decay": 8, "neutralization": "INDUSTRY"}},
    {"name": "combo2_d16", "expression": COMBO2,
     "theme": "Best combo, decay 16.",
     "settings": {"universe": "TOP3000", "decay": 16, "neutralization": "INDUSTRY"}},
    {"name": "combo2_d24", "expression": COMBO2,
     "theme": "Best combo, decay 24.",
     "settings": {"universe": "TOP3000", "decay": 24, "neutralization": "INDUSTRY"}},
    {"name": "combo2_d12_subind", "expression": COMBO2,
     "theme": "Best combo, decay 12, SUBINDUSTRY neutralization.",
     "settings": {"universe": "TOP3000", "decay": 12, "neutralization": "SUBINDUSTRY"}},
    {"name": "combo2_d16_subind", "expression": COMBO2,
     "theme": "Best combo, decay 16, SUBINDUSTRY.",
     "settings": {"universe": "TOP3000", "decay": 16, "neutralization": "SUBINDUSTRY"}},
    {"name": "triple_d12", "expression": TRIPLE,
     "theme": "S1+S2+S3 at the good decay 12.",
     "settings": {"universe": "TOP3000", "decay": 12, "neutralization": "INDUSTRY"}},
    {"name": "triple_d16_subind", "expression": TRIPLE,
     "theme": "S1+S2+S3, decay 16, SUBINDUSTRY.",
     "settings": {"universe": "TOP3000", "decay": 16, "neutralization": "SUBINDUSTRY"}},
    {"name": "combo2_w2cov_d12", "expression": f"-2 * zscore(ts_covariance(returns, volume, 20)) - group_zscore(ts_av_diff(close, 5), industry)",
     "theme": "Weight the high-fitness covariance-fade term 2x, decay 12.",
     "settings": {"universe": "TOP3000", "decay": 12, "neutralization": "INDUSTRY"}},
    {"name": "quad_d12", "expression": f"{TRIPLE} - zscore(divide(close, open))",
     "theme": "S1+S2+S3+S4 (adds intraday), decay 12.",
     "settings": {"universe": "TOP3000", "decay": 12, "neutralization": "INDUSTRY"}},
]
