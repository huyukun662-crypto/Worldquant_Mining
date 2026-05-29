"""Round-6 D0 candidates: change STRUCTURE, not just terms.

Additive zscore stacking plateaued at SH 1.43 and orthogonal-family terms
(low-vol) hurt. Round 6 changes the machinery:
  * rank / group_rank cores (bounded, outlier-robust -> often higher Sharpe);
  * a 1-day reversal core (-returns), the strongest short-horizon D0 signal;
  * ts_rank "near-recent-top" fade.
Each is paired with the proven covariance-fade. TOP3000, decay 16 (the sweet
spot), INDUSTRY. niche ops; no IV; no template reuse.
"""

COV = "ts_covariance(returns, volume, 20)"

def _s(decay=16, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut}

CANDIDATES = [
    # rank-based versions of the proven core
    {"name": "rank_core", "expression": f"-rank({COV}) - group_rank(ts_av_diff(close, 5), industry)",
     "theme": "Rank-based cov-fade + industry-rank reversal (robust).", "settings": _s()},
    {"name": "rank_core_d8", "expression": f"-rank({COV}) - group_rank(ts_av_diff(close, 5), industry)",
     "theme": "Same, decay 8.", "settings": _s(decay=8)},
    # 1-day reversal core (strongest short-horizon D0 signal)
    {"name": "cov_1drev", "expression": f"-zscore({COV}) - group_zscore(returns, industry)",
     "theme": "Cov-fade + 1-day industry-relative return reversal.", "settings": _s()},
    {"name": "cov_1drev_d8", "expression": f"-zscore({COV}) - group_zscore(returns, industry)",
     "theme": "Same, decay 8.", "settings": _s(decay=8)},
    {"name": "cov_1drev_rank", "expression": f"-rank({COV}) - group_rank(returns, industry)",
     "theme": "Rank-based cov-fade + 1-day return reversal.", "settings": _s()},
    # multi-horizon reversal blend + cov fade
    {"name": "cov_multirev", "expression": f"-zscore({COV}) - group_zscore(returns, industry) - group_zscore(ts_av_diff(close, 5), industry)",
     "theme": "Cov-fade + 1-day reversal + 5-day reversal (multi-horizon).", "settings": _s()},
    # ts_rank near-top fade + reversal
    {"name": "tsrank_rev", "expression": f"-zscore({COV}) - group_zscore(ts_rank(close, 10), industry)",
     "theme": "Cov-fade + 'near 10-day top' fade (ts_rank).", "settings": _s()},
    # strengthen cov-fade with ts_rank, plus reversal
    {"name": "tsrankcov_rev", "expression": f"-ts_rank({COV}, 60) - group_zscore(ts_av_diff(close, 5), industry)",
     "theme": "Temporal-rank cov-fade + 5-day reversal.", "settings": _s()},
]
