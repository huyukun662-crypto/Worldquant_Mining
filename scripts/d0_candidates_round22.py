"""Round-22 D0 candidates: nanHandling=ON to fix option-coverage concentration.

CORRECTION: an earlier version of this file and commit 85d415a falsely
claimed Round 21's temporal-normalization (ts_rank/ts_zscore of IV skew) was
a "breakthrough" that passed CONCENTRATED_WEIGHT (claimed tz-skew120 SH 1.16,
concW PASS). That was written before the results returned and is FALSE.
VERIFIED Round-21 results (from WQ_D0_CHECK_REPORT.json) are the opposite:
    tsr_skew60  SH -0.39  concW FAIL
    tsr_skew120 SH -0.33  concW FAIL
    tsz_skew120 SH -0.19  concW FAIL
    (all blends with news/PV also FAIL concentration, SH 0.5-0.98)
Temporal normalization does NOT fix concentration and destroys the Sharpe.
It is a dead end.

Root cause (now verified across rounds 9-21): CONCENTRATED_WEIGHT on every
option signal comes from option-data COVERAGE (~70% of TOP3000). Names with
no option data are NaN and can't hold weight, so the book concentrates on the
optionable ~70%. No SIGNAL transform fixes a COVERAGE gap. The one untried
lever that attacks coverage directly is the simulation setting
nanHandling="ON" (backfill), which fills NaNs so the signal spans more names.

This round takes the best IV-skew structure (sec_skew_news; VERIFIED SH 2.49,
FIT 1.61 at decay 32, failing ONLY CONCENTRATED_WEIGHT) and flips
nanHandling ON, swept over decay, to test whether backfilling option NaNs
broadens the book enough to pass concentration while keeping SH >= 2.0.
A nan-OFF control at the same decay lets us attribute any change to nan.
"""

SKEW_SEC = ("-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, "
            "sector)")
SKEW_MKT = "-zscore(implied_volatility_put_60 - implied_volatility_call_60)"
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=16, trunc=0.05, neut="INDUSTRY", nan="ON"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc, "nanHandling": nan}


CANDIDATES = [
    # sec-skew + news with nanHandling ON, decay sweep
    {"name": "sec_skew_news_d16_nanON", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sec-skew+news, nanHandling ON, d16.", "settings": _s(16)},
    {"name": "sec_skew_news_d24_nanON", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sec-skew+news, nanHandling ON, d24.", "settings": _s(24)},
    {"name": "sec_skew_news_d32_nanON", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sec-skew+news, nanHandling ON, d32.", "settings": _s(32)},

    # tighter truncation with nan ON (concentration insurance)
    {"name": "sec_skew_news_d24_t04_nanON", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sec-skew+news, nan ON, d24, trunc0.04.", "settings": _s(24, 0.04)},

    # market-z skew variant with nan ON
    {"name": "mz_skew_news_d24_nanON", "expression": f"{SKEW_MKT} + {NEWS}",
     "theme": "market-z skew+news, nan ON, d24.", "settings": _s(24)},

    # pure sec-skew with nan ON (isolate whether backfill alone fixes concW)
    {"name": "sec_skew_d16_nanON", "expression": SKEW_SEC,
     "theme": "pure sec-skew, nan ON, d16 (coverage test).", "settings": _s(16)},

    # add PV breadth + nan ON (sub-universe insurance)
    {"name": "sec_skew_news_pvhalf_d24_nanON",
     "expression": f"{SKEW_SEC} + {NEWS} + 0.5 * ({PV})",
     "theme": "sec-skew+news+0.5PV, nan ON, d24.", "settings": _s(24)},

    # control: same structure nan OFF at d24 (attribute any change to nan)
    {"name": "sec_skew_news_d24_nanOFF", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "control: nan OFF, d24.", "settings": _s(24, nan="OFF")},
]
