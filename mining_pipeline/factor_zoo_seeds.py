"""Seed expressions inspired by 10 quantitative factor libraries.

Per user spec (image-attached message): mine from these libraries
BUT explicitly avoid WorldQuant Alpha101. Each seed below is a
structural archetype from the named library, hand-translated to
FastExpr using the fields available in our 150-field WQ pool.

References:
    - Alpha360 / Multi-Factor Alphas    (volume-price patterns)
    - 国泰君安 191                       (short-term reversal / volume)
    - 通联数据 424                       (fundamental quality, growth)
    - Fama-French                       (size, value, momentum, profit, invest)
    - Barra (MSCI)                      (beta, vol, liquidity, growth, quality)
    - 聚宽 (JoinQuant), 米筐 (RiceQuant) (classical combos)
    - 华泰证券 (Huatai)                  (sentiment / news / event)
    - 盈余公告异象 (PEAD)                (post-earnings drift)

Each expression has an inline rationale tag for context. The pipeline
does NOT use the comments — they document intent only.
"""

ZOO_SEEDS: list[tuple[str, str]] = [
    # ---- Fama-French style factors ----
    ("FF-SMB-size",
        "rank(reverse(log(cap)))"),
    ("FF-HML-book-to-market",
        "rank(divide(subtract(assets, liabilities), cap))"),
    ("FF-RMW-profitability",
        "rank(divide(operating_income, assets))"),
    ("FF-CMA-investment",
        "rank(reverse(ts_returns(assets, 240)))"),
    ("FF-UMD-momentum-12m-1m",
        "rank(subtract(ts_returns(close, 240), ts_returns(close, 20)))"),

    # ---- Barra (MSCI) style factors ----
    ("Barra-residual-vol",
        "rank(reverse(unsystematic_risk_last_90_days))"),
    ("Barra-total-vol",
        "rank(reverse(ts_std_dev(returns, 60)))"),
    ("Barra-turnover-liquidity",
        "rank(reverse(divide(volume, sharesout)))"),
    ("Barra-beta-proxy",
        "rank(reverse(ts_corr(returns, news_spy_close, 60)))"),
    ("Barra-leverage",
        "rank(reverse(divide(debt, equity)))"),

    # ---- Quality / Cashflow (Tonglian-424, JoinQuant, RiceQuant) ----
    ("Tonglian-ROE",
        "rank(divide(operating_income, equity))"),
    ("Tonglian-CF-yield",
        "rank(divide(cashflow_op, cap))"),
    ("Tonglian-EBITDA-yield",
        "rank(divide(ebitda, enterprise_value))"),
    ("Tonglian-sales-growth",
        "rank(ts_returns(sales, 240))"),

    # ---- Alpha360 / GTJA-191 style price-volume ----
    ("Alpha360-short-reversal-5d",
        "rank(reverse(ts_returns(close, 5)))"),
    ("Alpha360-intraday-range",
        "rank(reverse(divide(subtract(high, low), close)))"),
    ("Alpha360-volume-momentum",
        "rank(ts_delta(log(volume), 20))"),
    ("Alpha360-Amihud-illiquidity",
        "rank(divide(abs(returns), multiply(close, volume)))"),
    ("GTJA-close-to-vwap",
        "rank(divide(close, vwap))"),

    # ---- Huatai / sentiment / news ----
    ("Huatai-news-momentum",
        "rank(ts_delta(snt_value, 5))"),
    ("Huatai-buzz-spike",
        "rank(ts_zscore(snt_buzz, 20))"),
    ("Huatai-news-gap-fade",
        "rank(reverse(subtract(news_eod_vwap, vwap)))"),

    # ---- Options-derived ----
    ("Option-PCR-fade",
        "rank(reverse(pcr_oi_270))"),
    ("Option-IV-skew",
        "rank(subtract(implied_volatility_put_270, implied_volatility_call_270))"),
    ("Option-realized-vs-implied",
        "rank(subtract(ts_std_dev(returns, 30), implied_volatility_call_10))"),

    # ---- PEAD / earnings surprise ----
    ("PEAD-netincome-revision",
        "rank(ts_delta(anl4_adjusted_netincome_ft, 60))"),
    ("PEAD-EBIT-revision",
        "rank(ts_delta(anl4_ebit_value, 60))"),

    # ---- Composite / multi-factor ----
    ("Combo-momentum-over-vol",
        "rank(divide(ts_returns(close, 240), ts_std_dev(returns, 60)))"),
    ("Combo-value-growth-model",
        "rank(mdl177_garpanalystmodel_qgp_vfpriceratio)"),
    ("Combo-mgmt-quality-model",
        "rank(mdl177_2_managementqualityfactor_saleicap)"),
]


def expressions() -> list[str]:
    """Just the expression strings, in fixed order."""
    return [expr for _, expr in ZOO_SEEDS]


if __name__ == "__main__":
    for tag, expr in ZOO_SEEDS:
        print(f"{tag:32s} {expr}")
