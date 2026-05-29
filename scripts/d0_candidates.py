"""Curated D0 (delay=0) alpha candidates for the submit-check workflow.

IMPORTANT: this account tier exposes only 66 operators (GET /operators).
Every expression below uses ONLY operators confirmed available on the tier,
verified signatures:
    ts_av_diff(x,d)            x - ts_mean(x,d)         (de-meaning)
    ts_arg_max(x,d) / ts_arg_min(x,d)                   (recency timing)
    kth_element(x,d,k)         k-th element in window    (robust anchor)
    days_from_last_change(x)                              (info staleness)
    ts_covariance(y,x,d) / ts_regression(y,x,d,lag,rettype)
    signed_power(x,y)          sign(x)*|x|**y            (concave transform)
    trade_when(x,y,z)          conditional exposure
    ts_quantile(x,d)           rolling quantile
    group_zscore(x,g) / group_neutralize(x,g)            (within-group)
    hump(x,h)                  turnover dampener
Regularization wrappers used: zscore / scale / winsorize / rank / hump /
group_zscore / group_neutralize.

Design constraints (per user spec):
  * delay = 0 only; concise; clear economic rationale.
  * niche operators (NOT the common ts_delta/ts_mean/rank-only combos).
  * NO implied-volatility (IV) / option fields -- price-volume + group only.
  * NOT reusing prior mined themes (volume-vol decay, adv20/low liquidity,
    reverse(low) reversal) and NEVER reusing Alpha101 / classical templates.

D0 signals are high-turnover, so fast signals carry larger `decay` / `hump`.
"""

CANDIDATES = [
    {
        "name": "avdiff_reversal_indneut",
        "expression": "group_neutralize(-zscore(ts_av_diff(close, 5)), industry)",
        "theme": "Short-term reversal: price deviation from its own 5d mean "
                 "(ts_av_diff), standardized, then industry-neutralized.",
        "settings": {"decay": 8, "neutralization": "INDUSTRY"},
    },
    {
        "name": "high_recency_momentum",
        "expression": "-zscore(ts_arg_max(close, 20))",
        "theme": "52-week-high style momentum: fewer days since the 20d high "
                 "(small ts_arg_max) = nearer the high -> keeps winning.",
        "settings": {"decay": 6, "neutralization": "SUBINDUSTRY"},
    },
    {
        "name": "low_recency_recovery",
        "expression": "zscore(ts_arg_min(close, 20))",
        "theme": "Recovery momentum: more days since the 20d low = the stock has "
                 "left its trough behind and is trending up.",
        "settings": {"decay": 6, "neutralization": "SUBINDUSTRY"},
    },
    {
        "name": "anchor_reversal_kth",
        "expression": "-zscore(divide(close, kth_element(close, 20, 5)))",
        "theme": "Reference-price reversal: price vs a robust anchor (5th element "
                 "of the last 20 days) -> reverts toward the anchor.",
        "settings": {"decay": 8, "neutralization": "SUBINDUSTRY"},
    },
    {
        "name": "info_staleness_fip",
        "expression": "-rank(days_from_last_change(close))",
        "theme": "Frog-in-the-pan: fewer days since price last changed = "
                 "continuous information diffusion -> persistent drift.",
        "settings": {"decay": 4, "neutralization": "INDUSTRY"},
    },
    {
        "name": "retvol_cov_fade",
        "expression": "-zscore(ts_covariance(returns, volume, 20))",
        "theme": "Return-volume covariance: high covariance = volume confirming "
                 "moves = crowded/overextended -> fade it.",
        "settings": {"decay": 8, "neutralization": "INDUSTRY"},
    },
    {
        "name": "vwap_resid_reversal",
        "expression": "-zscore(ts_regression(close, vwap, 20, lag=0, rettype=0))",
        "theme": "Idiosyncratic mispricing: residual of close regressed on vwap "
                 "(rettype=0) = transient deviation -> mean-reverts.",
        "settings": {"decay": 8, "neutralization": "SUBINDUSTRY"},
    },
    {
        "name": "concave_momentum",
        "expression": "zscore(signed_power(ts_delta(vwap, 10), 0.5))",
        "theme": "Outlier-tamed momentum: 10d vwap change passed through a "
                 "signed square-root so extreme moves do not dominate.",
        "settings": {"decay": 4, "neutralization": "INDUSTRY"},
    },
    {
        "name": "cond_reversal_tradewhen",
        "expression": "trade_when(ts_delta(volume, 1) > 0, -group_zscore(ts_av_diff(close, 5), industry), -1)",
        "theme": "Conditional reversal: take the industry-relative reversal bet "
                 "only on rising-volume days (trade_when); never force-exit.",
        "settings": {"decay": 8, "neutralization": "INDUSTRY"},
    },
    {
        "name": "quantile_extreme_fade",
        "expression": "hump(-zscore(ts_quantile(returns, 20)), 0.02)",
        "theme": "Extremeness fade: high rolling-quantile of recent return = "
                 "recent winner -> fade; hump caps turnover.",
        "settings": {"decay": 4, "neutralization": "INDUSTRY"},
    },
]
