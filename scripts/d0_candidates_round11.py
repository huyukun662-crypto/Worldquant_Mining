"""Round-11 D0 candidates: finish the skew+news blend into a SUBMITTABLE D0.

Round 10 winner:
    skew_news = SKEW + NEWS  (decay 8, INDUSTRY, trunc 0.08)
      -> SH 2.30, TO 0.463, FIT 1.26, self_corr 0.634
         FAILS: LOW_FITNESS (1.26<1.3), CONCENTRATED_WEIGHT, LOW_SUB_UNIVERSE_SHARPE

Sharpe (>2.0) and self-correlation (<0.7) already PASS. The three remaining
failures are all downstream of one root cause: option coverage ~0.70 puts
too much weight on liquid optionable names, which (a) concentrates weight,
(b) hollows out the sub-universe (illiquid names have no option data), and
(c) drags fitness via elevated turnover. Levers, each targeted:

  * LOW_FITNESS         -> raise decay 8 -> 12/16 : cuts TO 0.46 -> ~0.35,
                          fitness ~= 2.30*sqrt(r/to) rises above 1.3.
  * CONCENTRATED_WEIGHT -> lower truncation 0.08 -> 0.04/0.05 : caps the
                          per-name weight, spreading the book.
  * LOW_SUB_UNIVERSE_SH -> tilt weight toward NEWS (coverage 0.91, orthogonal,
                          standalone SH 1.68) and/or SUBINDUSTRY neutralize,
                          so the sub-universe gets real signal.
"""

SKEW = "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, industry)"
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=12, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- decay (fitness) x truncation (concentration) grid on skew+news ---
    {"name": "sn_d12_t05", "expression": f"{SKEW} + {NEWS}",
     "theme": "skew+news, decay12, trunc0.05.", "settings": _s(12, 0.05)},
    {"name": "sn_d16_t05", "expression": f"{SKEW} + {NEWS}",
     "theme": "decay16, trunc0.05.", "settings": _s(16, 0.05)},
    {"name": "sn_d12_t04", "expression": f"{SKEW} + {NEWS}",
     "theme": "decay12, trunc0.04 (tighter cap).", "settings": _s(12, 0.04)},
    {"name": "sn_d16_t04", "expression": f"{SKEW} + {NEWS}",
     "theme": "decay16, trunc0.04.", "settings": _s(16, 0.04)},

    # --- news-tilted for sub-universe breadth ---
    {"name": "sn_news15_d12", "expression": f"{SKEW} + 1.5 * ({NEWS})",
     "theme": "1.5x news (sub-universe breadth), d12 t05.", "settings": _s(12, 0.05)},
    {"name": "sn_news2_d12", "expression": f"{SKEW} + 2 * ({NEWS})",
     "theme": "2x news, d12 t05.", "settings": _s(12, 0.05)},

    # --- finer neutralization ---
    {"name": "sn_d12_t05_subind",
     "expression": "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, subindustry) "
                   "+ group_zscore(ts_mean(news_pct_120min, 5), subindustry)",
     "theme": "SUBINDUSTRY neutralize both legs.", "settings": _s(12, 0.05, "SUBINDUSTRY")},

    # --- small PV breadth leg purely to lift sub-universe sharpe ---
    {"name": "sn_pvhalf_d12", "expression": f"{SKEW} + {NEWS} + 0.5 * ({PV})",
     "theme": "skew+news+0.5PV breadth, d12 t05.", "settings": _s(12, 0.05)},
    {"name": "sn_news15_pvhalf_d12",
     "expression": f"{SKEW} + 1.5 * ({NEWS}) + 0.5 * ({PV})",
     "theme": "1.5x news + 0.5 PV breadth, d12 t05.", "settings": _s(12, 0.05)},
]
