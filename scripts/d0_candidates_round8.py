"""Round-8 D0 candidates: sweep the REVERSAL window (and cov window).

The reversal term in the champion uses ts_av_diff(close, 5). The classic
strong equity reversal is monthly (~21d); 5d may be sub-optimal. Sweep the
reversal horizon and the covariance horizon on the champion structure.
Champion: -zscore(ts_covariance(returns,volume,W)) - group_zscore(ts_av_diff(close,R), industry)
decay 16, INDUSTRY, trunc 0.08, TOP3000. PV-only, niche core, no IV.
"""

def _s(decay=16):
    return {"universe": "TOP3000", "decay": decay, "neutralization": "INDUSTRY",
            "truncation": 0.08}

def _expr(W, R):
    return (f"-zscore(ts_covariance(returns, volume, {W})) "
            f"- group_zscore(ts_av_diff(close, {R}), industry)")

CANDIDATES = [
    {"name": "rev10", "expression": _expr(20, 10),
     "theme": "Reversal window 10d.", "settings": _s()},
    {"name": "rev15", "expression": _expr(20, 15),
     "theme": "Reversal window 15d.", "settings": _s()},
    {"name": "rev22", "expression": _expr(20, 22),
     "theme": "Reversal window 22d (monthly reversal).", "settings": _s()},
    {"name": "rev22_cov10", "expression": _expr(10, 22),
     "theme": "Monthly reversal + 10d covariance.", "settings": _s()},
    {"name": "rev22_cov30", "expression": _expr(30, 22),
     "theme": "Monthly reversal + 30d covariance.", "settings": _s()},
    {"name": "rev22_d8", "expression": _expr(20, 22),
     "theme": "Monthly reversal, decay 8.", "settings": _s(decay=8)},
    {"name": "rev15_cov30", "expression": _expr(30, 15),
     "theme": "15d reversal + 30d covariance.", "settings": _s()},
    {"name": "rev10_cov10", "expression": _expr(10, 10),
     "theme": "10d reversal + 10d covariance (both faster).", "settings": _s()},
]
