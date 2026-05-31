"""Round-26 D0 candidates: factors ORTHOGONAL to the 3 submittable survivors.

The 3 found factors (skew0_news2_pv / news2_pv_skew0_07 / skew0_news_pv_s10)
all share the SAME three signal sources:
    news_pct_120min (news drift) + ts_covariance(returns,volume)/ts_av_diff(close)
    (PV reversal) + iv_put60-iv_call60 (option skew).
Goal now: mine factors built from DIFFERENT data families so they are
uncorrelated with those three. Families used here (none overlap the above):

  A. FUNDAMENTAL value/quality (cov 0.83): net_income, equity, ebit, assets,
     cashflow_op, cap  -> earnings/book/cashflow yield, profitability.
  B. ANALYST (cov 0.62): eps_mean, target_price_mean, rec_mean -> implied
     upside, EPS-revision momentum, recommendation.
  C. PURE-TECHNICAL PV that does NOT use cov(ret,vol) or av_diff(close):
     intraday range, Amihud illiquidity, vwap/close positioning, overnight gap.

Every leg is group_zscore-neutralized within industry then NaN-filled with the
proven if_else(is_nan(x),0,x) trick (fundamentals/analyst have 17-38% NaN), so
each is concentration-safe by construction. Probe standalone first to find
which orthogonal families carry an edge, then later rounds blend the winners
toward SH >= 2.0.
"""


def nf(x):
    """z-scored signal with NaN -> 0 (keeps full universe in the book)."""
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


# --- A. fundamental value / quality ---------------------------------
EY = nf(gz("divide(net_income, cap)"))          # earnings yield (value)
BP = nf(gz("divide(equity, cap)"))              # book-to-price (value)
CFY = nf(gz("divide(cashflow_op, cap)"))        # cashflow yield (value)
ROA = nf(gz("divide(ebit, assets)"))            # profitability (quality)
VALQ = f"{EY} + {BP} + {CFY} + {ROA}"           # value+quality composite

# --- B. analyst -----------------------------------------------------
TPUP = nf(gz("divide(anl4_target_price_mean, close)"))      # implied upside
EREV = nf(gz("ts_delta(anl4_eps_mean, 60)"))               # EPS revision mom
REC = nf(gz("-anl4_rec_mean"))                              # lower rec = buy

# --- C. pure-technical PV (orthogonal to my cov/av_diff legs) -------
RANGE = nf(gz("-divide(subtract(high, low), close)"))      # low-range -> long
ILLIQ = nf(gz("divide(abs(returns), volume)"))             # Amihud illiquidity
GAP = nf(gz("-divide(open, ts_delay(close, 1))"))          # overnight-gap rev


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    # A: fundamental
    {"name": "fund_earnings_yield", "expression": EY,
     "theme": "earnings yield (net_income/cap).", "settings": _s(8)},
    {"name": "fund_valq_composite", "expression": VALQ,
     "theme": "value+quality composite (EY+BP+CFY+ROA).", "settings": _s(8)},
    {"name": "fund_profitability", "expression": ROA,
     "theme": "profitability ebit/assets.", "settings": _s(8)},

    # B: analyst
    {"name": "anl_target_upside", "expression": TPUP,
     "theme": "analyst target/price implied upside.", "settings": _s(8)},
    {"name": "anl_eps_revision", "expression": EREV,
     "theme": "EPS-estimate revision momentum (60d).", "settings": _s(8)},
    {"name": "anl_recommendation", "expression": REC,
     "theme": "analyst recommendation (lower=buy).", "settings": _s(8)},

    # C: pure-technical PV
    {"name": "pv_range_reversal", "expression": RANGE,
     "theme": "intraday low-range -> long.", "settings": _s(8)},
    {"name": "pv_illiquidity", "expression": ILLIQ,
     "theme": "Amihud illiquidity premium.", "settings": _s(8)},

    # small orthogonal composites (diversify within new families)
    {"name": "anl_valq", "expression": f"{TPUP} + {EREV} + {VALQ}",
     "theme": "analyst + value/quality blend.", "settings": _s(8)},
]
