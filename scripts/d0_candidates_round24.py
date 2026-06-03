"""Round-24 D0 candidates: NaN-filled IV-skew injection into the safe base.

Round 23 disproved the "concentration scales with skew coefficient" idea AND
revealed the true mechanism (verified from WQ_D0_CHECK_REPORT.json):
    base_skew015 (coeff 0.15) -> SH 1.40, concW FAIL
    base_skew05  (coeff 0.50) -> SH 1.60, concW FAIL
Even at coeff 0.15 concentration FAILS and Sharpe drops BELOW the 1.75 base.

Why: `base + c*skew` is NaN on every name where skew is NaN (~30% of TOP3000
have no option data). NaN + number = NaN, so those names drop out of the book
entirely -> the book collapses onto the optionable ~70% (concentration) and
loses breadth (Sharpe falls). The coefficient is irrelevant; the NaN
PROPAGATION is the problem.

Fix: fill the skew leg's NaNs with 0 BEFORE adding, via to_nan(x, 0,
reverse=true) (NaN -> 0). Then:
  * non-optionable names keep their FULL base signal (skew contributes 0),
    so they stay in the book -> concentration spread restored, and
  * optionable names get base + a skew tilt -> borrow the skew edge.
This should keep concW PASS (book spans all names) while lifting SH past 2.0.

Sweep the (now safe to be larger) skew coefficient since the breadth penalty
is gone. group_backfill is also tried as an alternative NaN remedy.
"""

BASE = ("2 * (group_zscore(ts_mean(news_pct_120min, 5), industry)) "
        "+ -zscore(ts_covariance(returns, volume, 20)) "
        "- group_zscore(ts_av_diff(close, 5), industry)")
SKEW_RAW = ("-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, "
            "sector)")
# NaN -> 0 so the leg adds 0 (not NaN) on non-optionable names
SKEW0 = f"to_nan({SKEW_RAW}, 0, reverse=true)"
# alternative: backfill the raw skew within sector before z-scoring
SKEW_BF = ("-group_zscore(group_backfill(implied_volatility_put_60 "
           "- implied_volatility_call_60, sector, 60), sector)")
SKEW_BF0 = f"to_nan({SKEW_BF}, 0, reverse=true)"


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    # NaN-filled skew, coefficient sweep (breadth now preserved)
    {"name": "base_skew0_03", "expression": f"{BASE} + 0.3 * ({SKEW0})",
     "theme": "base + 0.3 NaN-filled skew.", "settings": _s(8)},
    {"name": "base_skew0_05", "expression": f"{BASE} + 0.5 * ({SKEW0})",
     "theme": "base + 0.5 NaN-filled skew.", "settings": _s(8)},
    {"name": "base_skew0_075", "expression": f"{BASE} + 0.75 * ({SKEW0})",
     "theme": "base + 0.75 NaN-filled skew.", "settings": _s(8)},
    {"name": "base_skew0_10", "expression": f"{BASE} + 1.0 * ({SKEW0})",
     "theme": "base + 1.0 NaN-filled skew.", "settings": _s(8)},

    # pure NaN-filled skew alone (does NaN->0 alone pass concentration?)
    {"name": "skew0_alone", "expression": SKEW0,
     "theme": "NaN-filled skew alone (coverage test).", "settings": _s(8)},

    # backfilled-skew variants
    {"name": "base_skewbf_05", "expression": f"{BASE} + 0.5 * ({SKEW_BF0})",
     "theme": "base + 0.5 backfilled+NaN0 skew.", "settings": _s(8)},

    # higher decay on the blend
    {"name": "base_skew0_05_d12", "expression": f"{BASE} + 0.5 * ({SKEW0})",
     "theme": "base + 0.5 NaN-filled skew, decay12.", "settings": _s(12)},

    # tighter truncation insurance at the strong coefficient
    {"name": "base_skew0_075_t03", "expression": f"{BASE} + 0.75 * ({SKEW0})",
     "theme": "base + 0.75 NaN-filled skew, trunc0.03.", "settings": _s(8, 0.03)},
]
