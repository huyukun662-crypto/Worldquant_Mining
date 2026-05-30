"""Round-17 D0 candidates: shrink the UNIVERSE so IV skew stops concentrating.

State after 16 rounds:
  * skew+news on TOP3000  -> SH 2.45-2.52, passes EVERYTHING except
    CONCENTRATED_WEIGHT (floor ~0.103, limit 0.10). Root cause: option fields
    cover only ~70% of TOP3000 (the small-caps have no listed options), so the
    optionable large-cap cluster holds >10% of the book.
  * concentration-safe news+PV (no option) tops out at SH ~1.75 < 2.0.

The untried lever: option coverage is a function of the UNIVERSE. In TOP3000
the bottom ~2000 names lack options; in TOP500/TOP1000 (liquid large-caps)
nearly every name is optionable. Restricting to a liquid universe should make
the IV-skew book broad again -> CONCENTRATED_WEIGHT may finally PASS while the
2.0+ Sharpe survives. (Counter-risk: fewer names = larger per-name weight, so
this must be measured, not assumed.)

Same winning expression as Round 13-14, swept across TOP1000 / TOP500 / TOP200.
"""

SKEW_SEC = "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, sector)"
SKEW_MKT = "-zscore(implied_volatility_put_60 - implied_volatility_call_60)"
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(universe="TOP1000", decay=16, trunc=0.05, neut="INDUSTRY"):
    return {"universe": universe, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # sector-skew + news across shrinking universes
    {"name": "sec_skew_news_TOP1000_d16", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "skew+news on TOP1000.", "settings": _s("TOP1000", 16, 0.05)},
    {"name": "sec_skew_news_TOP500_d16", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "skew+news on TOP500.", "settings": _s("TOP500", 16, 0.05)},
    {"name": "sec_skew_news_TOP200_d16", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "skew+news on TOP200.", "settings": _s("TOP200", 16, 0.05)},

    # market-z skew variant on TOP1000/500
    {"name": "mz_skew_news_TOP1000_d16", "expression": f"{SKEW_MKT} + {NEWS}",
     "theme": "market-z skew+news on TOP1000.", "settings": _s("TOP1000", 16, 0.05)},
    {"name": "mz_skew_news_TOP500_d16", "expression": f"{SKEW_MKT} + {NEWS}",
     "theme": "market-z skew+news on TOP500.", "settings": _s("TOP500", 16, 0.05)},

    # higher decay + tighter truncation on TOP1000 (concentration insurance)
    {"name": "sec_skew_news_TOP1000_d20_t04", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "skew+news TOP1000 d20 t04.", "settings": _s("TOP1000", 20, 0.04)},

    # add PV breadth on TOP1000 (sub-universe insurance)
    {"name": "sec_skew_news_pvhalf_TOP1000_d18",
     "expression": f"{SKEW_SEC} + {NEWS} + 0.5 * ({PV})",
     "theme": "skew+news+0.5PV on TOP1000.", "settings": _s("TOP1000", 18, 0.05)},

    # pure skew on TOP500 (does coverage alone fix concentration?)
    {"name": "sec_skew_TOP500_d12", "expression": f"{SKEW_SEC}",
     "theme": "pure sector-skew on TOP500 (coverage test).", "settings": _s("TOP500", 12, 0.05)},
]
