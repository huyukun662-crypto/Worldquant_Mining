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

# Building blocks - only WQ Brain pv fields actually exposed on this account
# (verified via constants/data_fields_union_USA.json). `dollar_volume` is
# NOT a WQ field (use multiply(close, volume) instead). The advN family on
# WQ Brain for this account is just `adv20`; adv5/adv60/adv120 are not
# exposed.
FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns",
          "cap", "sharesout", "adv20")

TS_OPS_1ARG = ("ts_zscore", "ts_rank", "ts_delta", "ts_mean",
               "ts_std_dev", "ts_decay_linear")  # ts_returns inaccessible on this account (2026-05)
TS_OPS_2ARG = ("ts_corr",)  # both args time-series; share a window

CS_OPS = ("rank", "zscore", "scale", "normalize")  # binary inaccessible on this account (2026-05)
ARITH_OPS = ("add", "subtract", "multiply", "divide")
ELEMWISE_UNARY = ("log", "abs", "reverse", "sign")  # s_log_1p inaccessible on this account (2026-05)

# v2: group_* wrappers do cross-sectional ops within a bucket
GROUP_OPS = ("group_rank", "group_zscore", "group_neutralize")
GROUP_FIELDS = ("market", "sector", "industry", "subindustry")

# v2: trade_when entry/exit triggers (lowers turnover, raises fitness)
TRIGGER_FIELDS = ("returns", "volume")
TRIGGER_THRESHOLDS = (0.02, 0.05, 0.10)

WINDOWS_DEFAULT = (3, 5, 10, 20, 40, 60)


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
    op = rng.choice(ARITH_OPS)
    a = _expr(rng, depth - 1)
    b = _expr(rng, depth - 1)
    return f"{op}({a}, {b})"


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
    # v2: 30% group_*(x, group_field), else CS scalar wrap.
    if rng.random() < 0.30:
        op = rng.choice(GROUP_OPS)
        g = rng.choice(GROUP_FIELDS)
        return f"{op}({core}, {g})"
    return f"{rng.choice(CS_OPS)}({core})"


_DEGENERATE_PATTERNS = (
    # subtract(x,x) / divide(x,x) / multiply(x, sign(x)) etc.
    # We just textually check the most common offenders that surfaced
    # in the n=25 run.
)


def _is_degenerate(expr: str) -> bool:
    """Reject structurally-degenerate expressions that always evaluate
    to 0 / NaN / divide-by-zero, observed in the n=25 D0 run."""
    import re
    # subtract(X, X) or divide(X, X) or add(X, -X) where X is the same leaf token
    for op in ("subtract", "divide"):
        # match op( token , token )  where token is a leaf identifier
        for m in re.finditer(rf"{op}\(\s*([a-z_]\w*)\s*,\s*([a-z_]\w*)\s*\)", expr):
            if m.group(1) == m.group(2):
                return True
    # divide(_, sign(cap)) -> denominator switches sign rarely, ~always 0
    if re.search(r"divide\([^,]+,\s*sign\(", expr):
        return True
    # divide(_, ts_delta(sign(...), _)) -> almost always 0
    if re.search(r"divide\([^,]+,\s*ts_delta\(\s*sign\(", expr):
        return True
    return False


def generate_one(rng: random.Random, max_depth: int = 3) -> str:
    core = _expr(rng, max_depth)
    # v2: pre-wrap with winsorize(_, 4) and/or ts_backfill(_, 5) probabilistically
    if rng.random() < 0.50:
        core = f"winsorize({core}, std=4)"
    if rng.random() < 0.30:
        core = f"ts_backfill({core}, 5)"
    out = _wrap(rng, core)
    # v2: 20% wrap with trade_when(trigger, alpha, -1)
    if rng.random() < 0.20:
        f = rng.choice(TRIGGER_FIELDS)
        th = rng.choice(TRIGGER_THRESHOLDS)
        out = f"trade_when(greater(abs({f}), {th}), {out}, -1)"
    return out


def generate(n: int, seed: int = 42, max_depth: int = 3) -> List[str]:
    rng = random.Random(seed)
    seen = set()
    out: List[str] = []
    attempts = 0
    while len(out) < n and attempts < n * 50:
        attempts += 1
        e = generate_one(rng, max_depth=max_depth)
        if _is_degenerate(e):
            continue
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
