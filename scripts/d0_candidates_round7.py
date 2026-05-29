"""Round-7 D0 candidates: tune the SETTINGS of the champion, not the formula.

Champion (all rounds): combo2 = -zscore(ts_covariance(returns,volume,20))
- group_zscore(ts_av_diff(close,5), industry), decay 16, INDUSTRY, trunc 0.08
-> SH 1.43, FIT 1.5, TO 0.226, self_corr 0.55; only LOW_SHARPE (needs >=2.0).

Every formula change so far lowered Sharpe or raised self-corr. The one
high-leverage knob NOT yet swept is `truncation`: lower truncation spreads
weight more evenly across names -> less idiosyncratic risk -> typically higher
Sharpe. Round 7 sweeps truncation (and a touch of decay), plus a trade_when
high-conviction gate. Same champion formula; D0; TOP3000.
"""

COMBO2 = ("-zscore(ts_covariance(returns, volume, 20)) "
          "- group_zscore(ts_av_diff(close, 5), industry)")

def _s(decay=16, neut="INDUSTRY", trunc=0.08):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}

CANDIDATES = [
    {"name": "combo2_t001", "expression": COMBO2,
     "theme": "Champion, truncation 0.01 (max diversification).", "settings": _s(trunc=0.01)},
    {"name": "combo2_t002", "expression": COMBO2,
     "theme": "Champion, truncation 0.02.", "settings": _s(trunc=0.02)},
    {"name": "combo2_t004", "expression": COMBO2,
     "theme": "Champion, truncation 0.04.", "settings": _s(trunc=0.04)},
    {"name": "combo2_t002_d12", "expression": COMBO2,
     "theme": "truncation 0.02, decay 12.", "settings": _s(decay=12, trunc=0.02)},
    {"name": "combo2_t002_d20", "expression": COMBO2,
     "theme": "truncation 0.02, decay 20.", "settings": _s(decay=20, trunc=0.02)},
    {"name": "combo2_t002_subind", "expression": COMBO2,
     "theme": "truncation 0.02, SUBINDUSTRY.", "settings": _s(neut="SUBINDUSTRY", trunc=0.02)},
    {"name": "combo2_t000", "expression": COMBO2,
     "theme": "truncation 0.0 (no truncation -> fully diversified).", "settings": _s(trunc=0.0)},
    {"name": "combo2_gate_t002",
     "expression": ("trade_when(ts_covariance(returns, volume, 20) > 0, "
                    "-zscore(ts_covariance(returns, volume, 20)) "
                    "- group_zscore(ts_av_diff(close, 5), industry), -1)"),
     "theme": "Champion gated to high-covariance (high-conviction) days.",
     "settings": _s(trunc=0.02)},
]
