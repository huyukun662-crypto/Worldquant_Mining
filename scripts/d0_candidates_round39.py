"""Round-39: NEW orthogonal d0 families -- social media + fresh analyst.

Rounds 36-38 proved that REMOVING the iv put-call skew caps a d0 blend of the
already-mined families (option-IV / news_pct / PV / est_epsr) at SH ~1.52. But
those rounds never touched two families that are available at d0/TOP3000 and are
structurally orthogonal to every survivor source:

  * socialmedia (8 usable MATRIX fields) -- sentiment + buzz, NEVER mined.
  * broader analyst estimates (est_fcf, est_ebitda, est_netprofit, ...) --
    only est_epsr was ever used.

Proven-dead families are deliberately excluded: news-event point signals
(news_indx_perf / react / settle / runup) were already shown to be high-turnover
(0.83-0.99) and individually weak, so no news-event leg appears here.

This is a DISCOVERY round: single-leg probes establish each new source's sign
and standalone d0 strength, then two orthogonal blends combine the best guesses.
Every leg is NaN-filled (option/social data is sparse -> concentration-safe) and
industry-neutral, matching the survivor recipe. delay=0, decay=8, trunc 0.05.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


def leg(sig):
    return nf(gz(sig))


# ---- single-source orthogonal legs (sign discovered empirically) ----
SOC_SENTVAL = leg("ts_mean(snt_value, 5)")          # snt_value = NEGATIVE sentiment
SOC_SENTVAL_NEG = leg("ts_mean(-snt_value, 5)")     # flip sign
SOC_BUZZRET = leg("ts_mean(snt_buzz_ret, 5)")
SOC_SCL_SENT = leg("ts_mean(scl12_sentiment, 5)")
SOC_SOCVAL = leg("ts_mean(snt_social_value, 5)")
SOC_BUZZ_MOM = leg("ts_delta(scl12_buzz, 5)")

AN_FCFY = leg("divide(est_fcf, close)")             # fwd FCF yield
AN_EBITDA_REV = leg("ts_delta(est_ebitda, 60)")     # EBITDA estimate revision
AN_NPY = leg("divide(est_netprofit, close)")        # fwd net-profit yield

# ---- orthogonal blends (best-guess signs; refined next round from singles) ----
# social-led: sentiment-flip + buzz-return + buzz-momentum
BLEND_SOCIAL = f"{SOC_SENTVAL_NEG} + {SOC_BUZZRET} + {SOC_BUZZ_MOM} + {SOC_SCL_SENT}"
# social + fresh-analyst yield/revision (fully orthogonal to all survivors)
BLEND_SOC_AN = (f"{SOC_SENTVAL_NEG} + {SOC_BUZZRET} + {AN_FCFY} "
                f"+ {AN_EBITDA_REV} + {AN_NPY}")


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": 0, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    {"name": "soc_sentval", "expression": SOC_SENTVAL,
     "theme": "social negative-sentiment, raw sign.", "settings": _s()},
    {"name": "soc_sentval_neg", "expression": SOC_SENTVAL_NEG,
     "theme": "social sentiment, flipped sign.", "settings": _s()},
    {"name": "soc_buzzret", "expression": SOC_BUZZRET,
     "theme": "social buzz return.", "settings": _s()},
    {"name": "soc_scl_sent", "expression": SOC_SCL_SENT,
     "theme": "scl12 sentiment.", "settings": _s()},
    {"name": "soc_socval", "expression": SOC_SOCVAL,
     "theme": "snt_social_value zscore-of-sentiment.", "settings": _s()},
    {"name": "soc_buzz_mom", "expression": SOC_BUZZ_MOM,
     "theme": "scl12 buzz momentum.", "settings": _s()},
    {"name": "an_fcfy", "expression": AN_FCFY,
     "theme": "fwd FCF yield (analyst).", "settings": _s()},
    {"name": "an_ebitda_rev", "expression": AN_EBITDA_REV,
     "theme": "EBITDA estimate revision.", "settings": _s()},
    {"name": "an_npy", "expression": AN_NPY,
     "theme": "fwd net-profit yield.", "settings": _s()},
    {"name": "blend_social", "expression": BLEND_SOCIAL,
     "theme": "social-only orthogonal blend.", "settings": _s()},
    {"name": "blend_soc_an", "expression": BLEND_SOC_AN,
     "theme": "social + fresh-analyst orthogonal blend.", "settings": _s()},
]
