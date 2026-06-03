"""Round-9 D0 candidates: ORTHOGONAL non-PV signal probes.

Rounds 4-8 proved the pure price/volume reversal+covariance structure
plateaus at WQ D0 Sharpe ~= 1.43 -- far below the delay=0 submit bar of
2.0. To break the plateau we must add signal that is *economically
orthogonal* to short-term reversal. This round probes each alternative
data family STANDALONE (sign + strength unknown a-priori) so Round 10 can
combine the winners with the PV core:

    PV core (known 1.43):
      -zscore(ts_covariance(returns, volume, 20))
      - group_zscore(ts_av_diff(close, 5), industry)

Families probed (all delay=0, TOP3000, INDUSTRY-neutralized, trunc 0.08):
  * option-implied vol  (cov ~0.70): put/call IV skew, IV momentum, term
  * analyst estimates   (cov ~0.74): EPS / net-profit revision momentum
  * social sentiment    (cov  1.00): level, momentum, attention(buzz)
  * news reaction       (cov ~0.91): 120-min price reaction over/under

Each probe is reported sign-explicit; the opposite sign is included where
the economic direction is genuinely ambiguous (skew, news reaction).
"""


def _s(decay=6):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": "INDUSTRY", "truncation": 0.08}


CANDIDATES = [
    # ---- option-implied volatility -------------------------------------
    # Put-call IV skew: elevated put IV = priced downside fear. As a
    # contrarian signal, high skew -> subsequent outperformance.
    {"name": "iv_skew60",
     "expression": "group_zscore(implied_volatility_put_60 - implied_volatility_call_60, industry)",
     "theme": "ATM put-call IV skew (60d), long high-skew.", "settings": _s(8)},
    {"name": "iv_skew60_neg",
     "expression": "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, industry)",
     "theme": "Skew, opposite sign.", "settings": _s(8)},
    # IV momentum: rising implied vol = rising risk premium -> reversal.
    {"name": "iv_mom_neg",
     "expression": "-group_zscore(ts_delta(implied_volatility_mean_180, 5), industry)",
     "theme": "Falling IV (180d) bullish.", "settings": _s(6)},
    # IV term structure: steep (180>60) = calm now / risk later.
    {"name": "iv_term",
     "expression": "group_zscore(implied_volatility_call_180 - implied_volatility_call_60, industry)",
     "theme": "Call IV term slope (180-60).", "settings": _s(8)},

    # ---- analyst estimate revisions (PEAD / revision momentum) ---------
    {"name": "anl_eps_rev",
     "expression": "group_zscore(ts_delta(est_epsr, 22), industry)",
     "theme": "EPS estimate revision momentum (22d).", "settings": _s(12)},
    {"name": "anl_eps_rev_fast",
     "expression": "group_zscore(ts_delta(est_epsr, 10), industry)",
     "theme": "EPS revision momentum (10d).", "settings": _s(8)},
    {"name": "anl_np_rev",
     "expression": "group_zscore(ts_delta(est_netprofit, 22), industry)",
     "theme": "Net-profit estimate revision momentum.", "settings": _s(12)},

    # ---- social sentiment (full coverage) -----------------------------
    {"name": "snt_level",
     "expression": "group_zscore(scl12_sentiment, industry)",
     "theme": "Social sentiment level.", "settings": _s(4)},
    {"name": "snt_mom",
     "expression": "group_zscore(ts_delta(scl12_sentiment, 5), industry)",
     "theme": "Social sentiment momentum (5d).", "settings": _s(4)},
    {"name": "buzz_rev",
     "expression": "-group_zscore(scl12_buzz, industry)",
     "theme": "High social attention -> reversal.", "settings": _s(4)},
    {"name": "snt_social_val",
     "expression": "group_zscore(snt_social_value, industry)",
     "theme": "Sentiment z-score field, level.", "settings": _s(4)},

    # ---- news reaction -------------------------------------------------
    {"name": "news_overreact",
     "expression": "-group_zscore(news_pct_120min, industry)",
     "theme": "Fade 120-min post-news move.", "settings": _s(4)},
    {"name": "news_mom",
     "expression": "group_zscore(news_pct_120min, industry)",
     "theme": "Follow 120-min post-news move.", "settings": _s(4)},
]
