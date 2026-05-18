"""Random alpha expression generator.

CRITICAL CONSTRAINT (per user spec): MUST NOT reuse any expression from
`worldquant_mining.factor_templates` (Alpha101 + classical factors). Every
expression here is generated fresh by sampling random combinations of
operators × PV fields × lookback hyperparameters.

Each generated expression has the form:

    expr := <wrapper>(<core>)
    core := <leaf> | <ts_op>(<leaf>[, d])
                   | <bin_op>(<core>, <core>)
                   | <decay>(<core>, d)

The lookbacks in `d` are *placeholder hyperparameters* that the search
stage (`search.py`) will refine via Bayes / grid. The generator always
emits a finite set of {3, 5, 10, 20, 40, 60} as initial guesses; the
search stage replaces those with optimized values.
"""

from __future__ import annotations

import hashlib
import random
from typing import List, Tuple

# Building blocks. PV fields verified against the D0/TOP1000 data-field
# snapshot in `constants/data_fields_cache_USA_0_TOP1000.json`. The
# non-PV fields below are picked from that same snapshot, filtered to
# MATRIX type with high date-coverage and *low* userCount (low userCount
# helps with MATCHES_COMPETITION / SELF_CORRELATION on submit). The advN
# family is just `adv20` on this universe; `adv5/60/120` are unavailable.
PV_FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns",
             "cap", "sharesout", "adv20")
# D0-extended fields — verified present at (USA, delay=0, TOP1000).
OPTION_FIELDS = ("historical_volatility_60", "historical_volatility_120",
                 "parkinson_volatility_60", "parkinson_volatility_120")
NEWS_FIELDS = ("news_eod_high", "news_eod_low", "news_max_dn_ret",
               "news_max_up_ret", "news_low_exc_stddev", "news_main_vwap")
ANALYST_FIELDS = ("est_epsr", "est_ebit", "est_cashflow_op",
                  "est_netprofit", "est_tot_assets")
SOCIAL_FIELDS = ("scl12_buzz", "scl12_sentiment", "snt_social_value",
                 "snt_social_volume")
FIELDS = PV_FIELDS + OPTION_FIELDS + NEWS_FIELDS + ANALYST_FIELDS + SOCIAL_FIELDS

# ts_returns and ts_corr also tier-gated on this account.
TS_OPS_1ARG = ("ts_zscore", "ts_rank", "ts_delta", "ts_mean",
               "ts_std_dev", "ts_decay_linear")
TS_OPS_2ARG: tuple[str, ...] = ()

CS_OPS = ("rank", "zscore", "scale", "normalize")  # wrappers
ARITH_OPS = ("add", "subtract", "multiply", "divide")
# Tier-gated on this account (HTTP 400 "inaccessible or unknown operator"):
# s_log_1p, vector_neut, trade_when, winsorize, signed_power, ts_arg_max,
# ts_arg_min — all confirmed gated. Generator stays on the verified subset.
ELEMWISE_UNARY = ("log", "abs", "reverse", "sign")
SPECIAL_OPS: tuple[str, ...] = ()

# D0 favors short windows (intraday-ish; long lookbacks just lag the
# market). The Optuna search in wq_pipeline still refines these.
WINDOWS_DEFAULT = (3, 5, 7, 10, 15, 20)


def _leaf(rng: random.Random) -> str:
    return rng.choice(FIELDS)


def _ts_call(rng: random.Random, depth: int) -> str:
    op = rng.choice(TS_OPS_1ARG + TS_OPS_2ARG)
    if op in TS_OPS_2ARG:
        a = _leaf(rng)
        b = _leaf(rng)
        while a == b:
            b = _leaf(rng)
        d = rng.choice(WINDOWS_DEFAULT)
        return f"{op}({a}, {b}, {d})"
    inner = _expr(rng, max(depth - 1, 0)) if depth > 1 else _leaf(rng)
    d = rng.choice(WINDOWS_DEFAULT)
    return f"{op}({inner}, {d})"


def _arith(rng: random.Random, depth: int) -> str:
    # WQ Brain validates units; add/subtract/multiply across heterogeneous
    # fields (e.g. price + sentiment) rejects with "Incompatible unit".
    # Wrap each operand in rank(...) so both sides become dimensionless
    # cross-sectional ranks, which add/subtract/multiply/divide cleanly.
    op = rng.choice(ARITH_OPS)
    a = _expr(rng, depth - 1)
    b = _expr(rng, depth - 1)
    return f"{op}(rank({a}), rank({b}))"


def _expr(rng: random.Random, depth: int) -> str:
    if depth <= 0:
        return _leaf(rng)
    r = rng.random()
    if r < 0.55:
        return _ts_call(rng, depth)
    if r < 0.80:
        return _arith(rng, depth)
    if r < 0.92:
        inner = _expr(rng, depth - 1)
        return f"{rng.choice(ELEMWISE_UNARY)}({inner})"
    return _leaf(rng)


def _wrap(rng: random.Random, core: str) -> str:
    # Wrap final output with a cross-sectional op for L/S scaling, and
    # half the time also smooth with ts_decay_linear / ts_mean to keep
    # turnover within WQ's <0.7 cap (TO is the killer at D0).
    cs = rng.choice(CS_OPS)
    if rng.random() < 0.5:
        smooth = rng.choice(("ts_decay_linear", "ts_mean"))
        d = rng.choice((5, 8, 10, 15, 20))
        return f"{cs}({smooth}({core}, {d}))"
    return f"{cs}({core})"


# D0-shaped skeletons — pattern-shaped, NOT value-shaped (no Alpha101
# or classical-factor formula copied verbatim). The {F}/{N}/{D} slots
# are filled at sample time and the integer windows remain free for the
# Optuna search in wq_pipeline. Per CLAUDE.md "no template reuse" rule:
# these are search-space priors, not finished factors.
D0_SKELETONS = (
    "rank(ts_rank(divide({F}, close), {D}))",
    "ts_decay_linear(ts_zscore(divide(close, vwap), {D}), {D})",
    "rank(ts_delta(divide({F}, {G}), {D}))",
    "ts_decay_linear(rank(divide({F}, {G})), {D})",
    "scale(ts_mean(ts_decay_linear(divide({F}, {G}), {D}), {D}))",
    "zscore(ts_decay_linear(ts_mean(ts_std_dev({F}, {D}), {D}), {D}))",
    "rank(ts_zscore(ts_delta(reverse({F}), {D}), {D}))",
    "rank(ts_decay_linear(ts_delta(divide({F}, ts_mean({G}, {D})), {D}), {D}))",
)


def _fill_skeleton(rng: random.Random, sk: str) -> str:
    out = sk
    # Each {F}/{G} gets an independent field draw.
    while "{F}" in out:
        out = out.replace("{F}", rng.choice(FIELDS), 1)
    while "{G}" in out:
        out = out.replace("{G}", rng.choice(FIELDS), 1)
    while "{D}" in out:
        out = out.replace("{D}", str(rng.choice(WINDOWS_DEFAULT)), 1)
    # Wrap in a cross-sectional op for consistent scaling.
    return f"{rng.choice(CS_OPS)}({out})"


def generate_one(rng: random.Random, max_depth: int = 3) -> str:
    # Mix random construction with D0 skeleton draws so the search both
    # explores broadly and concentrates near known-good shapes.
    if rng.random() < 0.5:
        return _fill_skeleton(rng, rng.choice(D0_SKELETONS))
    return _wrap(rng, _expr(rng, max_depth))


def generate(n: int, seed: int = 42, max_depth: int = 3) -> List[str]:
    rng = random.Random(seed)
    seen = set()
    out: List[str] = []
    while len(out) < n:
        e = generate_one(rng, max_depth=max_depth)
        h = hashlib.md5(e.encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append(e)
    return out


def _is_standalone_int_at(expr: str, i: int) -> bool:
    """A digit at position `i` is a standalone integer literal (not part
    of an identifier like `adv120`) iff the preceding character is not
    alphanumeric / underscore.
    """
    if i == 0:
        return True
    prev = expr[i - 1]
    return not (prev.isalnum() or prev == "_")


def parameterize(expr: str, windows: dict) -> str:
    """Replace standalone integer literals (not embedded in identifiers
    like `adv120`) at known positions with values from `windows`.

    `windows` is a dict { 0: 5, 1: 20, ... } mapping the i-th *standalone*
    integer literal occurrence (left to right) in `expr` to a new value.
    """
    out = []
    i = 0
    n = len(expr)
    seen_ints = 0
    while i < n:
        ch = expr[i]
        if ch.isdigit() and _is_standalone_int_at(expr, i):
            k = i
            while k < n and (expr[k].isdigit() or expr[k] == '.'):
                k += 1
            tok = expr[i:k]
            if "." not in tok:
                if seen_ints in windows:
                    tok = str(int(windows[seen_ints]))
                seen_ints += 1
            out.append(tok)
            i = k
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def integer_positions(expr: str) -> List[int]:
    """Return the indices (0-based) of standalone integer literals in expr,
    skipping digits embedded in identifiers like `adv120`.
    """
    pos: List[int] = []
    seen = 0
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isdigit() and _is_standalone_int_at(expr, i):
            k = i
            while k < n and (expr[k].isdigit() or expr[k] == '.'):
                k += 1
            tok = expr[i:k]
            if "." not in tok:
                pos.append(seen)
            seen += 1
            # advance past the integer
            i = k
        elif ch.isdigit():
            # digit inside an identifier - skip without counting
            while i < n and (expr[i].isdigit() or expr[i] == '.'):
                i += 1
        else:
            i += 1
    return pos


if __name__ == "__main__":
    for e in generate(10, seed=1):
        print(e)
