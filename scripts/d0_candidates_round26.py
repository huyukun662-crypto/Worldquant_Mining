"""Round-26 D0 candidates: factors ORTHOGONAL to the 3 submittable survivors.

The 3 found factors all share the SAME three signal sources:
    news_pct_120min (news drift) + ts_covariance(returns,volume)/ts_av_diff(close)
    (PV reversal) + iv_put60-iv_call60 (option skew).
Round 26 mines DIFFERENT data families so the new alphas are uncorrelated:

  A. FUNDAMENTAL value/quality (cov ~0.50): income, equity, cashflow_op, ebit,
     assets, sales -> earnings/book/cashflow yield, profitability.
  B. ANALYST estimates (cov 0.67-0.79): est_epsr, est_netprofit,
     est_bookvalue_ps -> forward earnings yield + estimate-revision momentum.
  C. SOCIAL MEDIA (cov 0.86-1.00): scl12_sentiment, scl12_buzz,
     snt_social_value -> retail sentiment & buzz (NOT news price drift).
  D. PURE-TECHNICAL PV NOT using cov(ret,vol)/av_diff: intraday range, Amihud
     illiquidity, overnight gap.

Every leg is group_zscore(industry)-neutralized then NaN-filled with the proven
if_else(is_nan(x),0,x) trick (fundamentals/analyst carry NaN), so each is
concentration-safe by construction. Standalone probes find which orthogonal
families carry an edge; later rounds blend the winners toward SH >= 2.0.

Field names verified against constants/data_fields_cache_USA_0_TOP3000.json
(note: it is `income` not `net_income`; analyst fields are `est_*` not `anl4_*`
and there is NO target-price/recommendation field on this tier).
"""


def nf(x):
    """z-scored signal with NaN -> 0 (keeps full universe in the book)."""
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


# --- A. fundamental value / quality ---------------------------------
EY = nf(gz("divide(income, cap)"))           # earnings yield
BP = nf(gz("divide(equity, cap)"))           # book-to-price
CFY = nf(gz("divide(cashflow_op, cap)"))     # cashflow yield
ROA = nf(gz("divide(ebit, assets)"))         # profitability
SP = nf(gz("divide(sales, cap)"))            # sales-to-price
VALQ = f"{EY} + {BP} + {CFY} + {ROA}"        # value+quality composite

# --- B. analyst estimates -------------------------------------------
FEY = nf(gz("divide(est_epsr, close)"))            # forward earnings yield
EREV = nf(gz("ts_delta(est_netprofit, 60)"))       # estimate-revision momentum
FBP = nf(gz("divide(est_bookvalue_ps, close)"))    # forward book-to-price

# --- C. social media ------------------------------------------------
SENT = nf(gz("scl12_sentiment"))             # social sentiment
BUZZ = nf(gz("scl12_buzz"))                  # relative sentiment volume
SNTZ = nf(gz("snt_social_value"))            # z-score of sentiment
SOCIAL = f"{SENT} + {SNTZ}"                  # sentiment composite

# --- D. pure-technical PV (orthogonal to cov/av_diff legs) ----------
RANGE = nf(gz("-divide(subtract(high, low), close)"))   # low-range -> long
ILLIQ = nf(gz("divide(abs(returns), volume)"))          # Amihud illiquidity
GAP = nf(gz("-divide(open, ts_delay(close, 1))"))       # overnight-gap rev


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    # A: fundamental
    {"name": "fund_earnings_yield", "expression": EY,
     "theme": "earnings yield income/cap.", "settings": _s(8)},
    {"name": "fund_valq_composite", "expression": VALQ,
     "theme": "value+quality (EY+BP+CFY+ROA).", "settings": _s(8)},

    # B: analyst
    {"name": "anl_fwd_eyield", "expression": FEY,
     "theme": "forward earnings yield est_epsr/close.", "settings": _s(8)},
    {"name": "anl_estrev", "expression": EREV,
     "theme": "estimate-revision momentum (est_netprofit 60d).", "settings": _s(8)},

    # C: social media
    {"name": "soc_sentiment", "expression": SENT,
     "theme": "social sentiment.", "settings": _s(8)},
    {"name": "soc_composite", "expression": SOCIAL,
     "theme": "sentiment + z-sentiment.", "settings": _s(8)},

    # D: pure-technical PV
    {"name": "pv_range_reversal", "expression": RANGE,
     "theme": "intraday low-range -> long.", "settings": _s(8)},
    {"name": "pv_illiquidity", "expression": ILLIQ,
     "theme": "Amihud illiquidity premium.", "settings": _s(8)},

    # cross-family composite (all orthogonal to the survivors)
    {"name": "fund_anl_soc", "expression": f"{VALQ} + {FEY} + {SOCIAL}",
     "theme": "value/quality + analyst + social blend.", "settings": _s(8)},
]
