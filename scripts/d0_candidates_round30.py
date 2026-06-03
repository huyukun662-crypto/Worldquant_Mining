"""Round-30 D0 candidates: hunt a STRONG single orthogonal leg (>1.5 standalone).

Round 29 plateaued at SH ~1.48 because I was stacking WEAK legs (each 0.6-0.9).
The 3 survivors reached 2.0 because the skew leg ALONE was ~2.17. To break past
2.0 with an uncorrelated alpha I need a strong SINGLE orthogonal leg, then
diversify it lightly. This round probes strong candidate forms standalone, all
NaN-filled + industry-neutral, none using the survivors' signal sources:

  A. Well-built SHORT-TERM REVERSAL (the classic strong D0 edge):
     - REV5    = -ts_zscore(returns, 5)        recent-return reversal
     - REVVWAP = -(close/vwap - 1) decayed     vwap reversion
     - REVRANK = -ts_rank(returns, 10)
  B. RESIDUAL reversal: ts_regression residual of close on volume.
  C. OPTION call-side momentum (distinct from put-call skew):
     - CALLMOM = ts_delta(iv_call_60, 20)
     - CPRATIO_MOM = ts_delta(iv_call_60/iv_put_60, 20)  ratio momentum
  D. Stronger IV momentum variants (best Round-27 leg was ivmom20 0.86):
     - IVMOM10, IVMOM_RANK
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVC = "implied_volatility_call_60"
IVP = "implied_volatility_put_60"
IVM = "implied_volatility_mean_60"

# A. short-term reversal forms
REV5 = nf(gz("-ts_zscore(returns, 5)"))
REVVWAP = nf(gz("-divide(subtract(close, vwap), vwap)"))
REVRANK = nf(gz("-ts_rank(returns, 10)"))
REV1 = nf(gz("-returns"))
# B. residual reversal
RESID = nf(gz("-ts_regression(returns, volume, 20, rettype=0)"))
# C. option call-side momentum (not the put-call skew)
CALLMOM = nf(gz(f"ts_delta({IVC}, 20)"))
CPRMOM = nf(gz(f"ts_delta(divide({IVC}, {IVP}), 20)"))
# D. stronger IV momentum
IVMOM10 = nf(gz(f"ts_delta({IVM}, 10)"))
IVMOM_RANK = nf(gz(f"ts_rank(ts_delta({IVM}, 20), 60)"))


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    {"name": "rev5", "expression": REV5,
     "theme": "5d return reversal (zscore).", "settings": _s(8)},
    {"name": "rev1", "expression": REV1,
     "theme": "1d return reversal.", "settings": _s(8)},
    {"name": "revrank", "expression": REVRANK,
     "theme": "10d return-rank reversal.", "settings": _s(8)},
    {"name": "resid_rev", "expression": RESID,
     "theme": "regression-residual reversal.", "settings": _s(8)},
    {"name": "callmom", "expression": CALLMOM,
     "theme": "IV-call momentum 20d.", "settings": _s(8)},
    {"name": "cpr_mom", "expression": CPRMOM,
     "theme": "call/put IV ratio momentum.", "settings": _s(8)},
    {"name": "ivmom10", "expression": IVMOM10,
     "theme": "IV momentum 10d.", "settings": _s(8)},
    {"name": "ivmom_rank", "expression": IVMOM_RANK,
     "theme": "ts_rank of IV momentum.", "settings": _s(8)},
]
