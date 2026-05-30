"""Round-23 D0 candidates: small-weight IV-skew injection into the safe base.

VERIFIED state after 22 rounds (all numbers from WQ_D0_CHECK_REPORT.json):
  * Best concentration-SAFE candidate: news2_pv_d8, SH 1.75, concW PASS,
    self_corr 0.357. Blocked only by LOW_SHARPE (<2.0).
  * Best IV-skew candidate: sec_skew_news, SH 2.49, but FAILS
    CONCENTRATED_WEIGHT because option data covers ~70% of TOP3000.
  * nanHandling=ON does NOT help (Round 22: nan ON == nan OFF, bit-identical).

Untried lever: CONCENTRATED_WEIGHT scales with how much book weight the
optionable names carry, which scales with the skew leg's COEFFICIENT. The
safe base alone has concentration well under the limit; the full skew blend
sits just over it. So there should be a coefficient c* where:
    safe_base + c * skew_leg
still passes concentration (optionable names don't dominate) yet borrows
enough of the skew's strong edge to push SH from 1.75 past 2.0.

This round sweeps c in {0.15, 0.25, 0.35, 0.5} on the sector-skew leg, plus a
couple of decay/weight variants. The base and the skew leg are the exact
verified-best forms.
"""

BASE = ("2 * (group_zscore(ts_mean(news_pct_120min, 5), industry)) "
        "+ -zscore(ts_covariance(returns, volume, 20)) "
        "- group_zscore(ts_av_diff(close, 5), industry)")
SKEW = ("-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, "
        "sector)")


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    # coefficient sweep on the skew leg (find the concentration boundary)
    {"name": "base_skew015", "expression": f"{BASE} + 0.15 * ({SKEW})",
     "theme": "safe base + 0.15 skew.", "settings": _s(8)},
    {"name": "base_skew025", "expression": f"{BASE} + 0.25 * ({SKEW})",
     "theme": "safe base + 0.25 skew.", "settings": _s(8)},
    {"name": "base_skew035", "expression": f"{BASE} + 0.35 * ({SKEW})",
     "theme": "safe base + 0.35 skew.", "settings": _s(8)},
    {"name": "base_skew05", "expression": f"{BASE} + 0.5 * ({SKEW})",
     "theme": "safe base + 0.50 skew.", "settings": _s(8)},

    # tighter truncation lowers per-name weight -> helps concentration
    {"name": "base_skew025_t03", "expression": f"{BASE} + 0.25 * ({SKEW})",
     "theme": "base + 0.25 skew, trunc 0.03.", "settings": _s(8, 0.03)},
    {"name": "base_skew035_t03", "expression": f"{BASE} + 0.35 * ({SKEW})",
     "theme": "base + 0.35 skew, trunc 0.03.", "settings": _s(8, 0.03)},

    # higher decay smooths the skew leg (lower turnover, may dilute concentration)
    {"name": "base_skew025_d12", "expression": f"{BASE} + 0.25 * ({SKEW})",
     "theme": "base + 0.25 skew, decay 12.", "settings": _s(12)},

    # subindustry-neutralize the skew (finer groups spread the weight)
    {"name": "base_skew025_subind",
     "expression": (BASE + " + 0.25 * (-group_zscore(implied_volatility_put_60 "
                    "- implied_volatility_call_60, subindustry))"),
     "theme": "base + 0.25 subindustry-skew.", "settings": _s(8)},
]
