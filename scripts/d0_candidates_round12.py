"""Round-12 D0 candidates: kill the last failure -- CONCENTRATED_WEIGHT.

Round 11 left exactly ONE blocker. The whole skew+news family passes
SH>2.0, FIT>1.3, TO<0.7, self_corr<0.7 and (at decay 12, 1x news)
LOW_SUB_UNIVERSE_SHARPE -- but every variant FAILS CONCENTRATED_WEIGHT:

    sn_d12_t05  concentration value 0.1156  (limit 0.10)
    sn_d12_t04  concentration value 0.1123  -> lowering truncation barely moved it
    sn_news15   concentration value 0.1098  -> MORE news weight helps, but 2x news
                                              breaks FIT (1.16) and sub-universe (0.93)

So per-name truncation is the wrong lever (0.05->0.04 shaved only 0.003) and
news-tilting hits a wall. The concentration is driven by the heavy TAIL of the
IV-skew z-score piling weight onto a few liquid optionable large-caps. The fix
is to FLATTEN that tail at the signal level, which truncation cannot do:

  * winsorize(group_zscore(skew), std=k) -- clip the z-score tail at +/-k std,
    preserving the ranking but removing the extreme weights. Surgical; should
    keep Sharpe.
  * group_rank(skew, industry)           -- replace the skew leg with a uniform
    in-industry rank: maximally flat weights, strongest concentration kill,
    at some Sharpe cost.

News leg kept (orthogonal, broad coverage); decay 12/16 keeps FIT headroom.
"""

NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _skew_wins(std):
    return (f"-winsorize(group_zscore(implied_volatility_put_60 "
            f"- implied_volatility_call_60, industry), std={std})")


SKEW_RANK = "-group_rank(implied_volatility_put_60 - implied_volatility_call_60, industry)"


def _s(decay=16, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- winsorize the skew z-score tail (surgical) --------------------
    {"name": "wins25_news_d16", "expression": f"{_skew_wins(2.5)} + {NEWS}",
     "theme": "winsorize skew std2.5 + news, d16 t05.", "settings": _s(16, 0.05)},
    {"name": "wins20_news_d16", "expression": f"{_skew_wins(2.0)} + {NEWS}",
     "theme": "winsorize skew std2.0 (tighter) + news.", "settings": _s(16, 0.05)},
    {"name": "wins15_news_d16", "expression": f"{_skew_wins(1.5)} + {NEWS}",
     "theme": "winsorize skew std1.5 + news.", "settings": _s(16, 0.05)},
    {"name": "wins20_news_d16_t04", "expression": f"{_skew_wins(2.0)} + {NEWS}",
     "theme": "winsorize std2.0 + news, trunc0.04.", "settings": _s(16, 0.04)},
    {"name": "wins20_news15_d16", "expression": f"{_skew_wins(2.0)} + 1.5 * ({NEWS})",
     "theme": "winsorize std2.0 + 1.5x news.", "settings": _s(16, 0.05)},

    # --- rank the skew leg (maximally flat) ----------------------------
    {"name": "rank_skew_news_d16", "expression": f"{SKEW_RANK} + {NEWS}",
     "theme": "group_rank skew + zscore news, d16 t05.", "settings": _s(16, 0.05)},
    {"name": "rank_skew_news_d12", "expression": f"{SKEW_RANK} + {NEWS}",
     "theme": "group_rank skew + news, d12 t05.", "settings": _s(12, 0.05)},

    # --- winsorized skew + small PV breadth (sub-universe insurance) ----
    {"name": "wins20_news_pvhalf_d16",
     "expression": f"{_skew_wins(2.0)} + {NEWS} + 0.5 * ({PV})",
     "theme": "winsorize std2.0 + news + 0.5PV breadth.", "settings": _s(16, 0.05)},
]
