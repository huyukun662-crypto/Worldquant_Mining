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
               "ts_std_dev", "ts_returns", "ts_decay_linear")
TS_OPS_2ARG = ("ts_corr",)  # both args time-series; share a window

CS_OPS = ("rank", "zscore", "scale", "normalize")  # wrappers
ARITH_OPS = ("add", "subtract", "multiply", "divide")
ELEMWISE_UNARY = ("log", "abs", "reverse", "sign", "s_log_1p")

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
    # Always wrap final output with a cross-sectional op so the signal is
    # appropriately scaled for the long-short backtest.
    wrap = rng.choice(CS_OPS)
    return f"{wrap}({core})"


def generate_one(rng: random.Random, max_depth: int = 3) -> str:
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


# =============================================================================
# D0 expression generator
# =============================================================================
# Generates FASTEXPR strings to submit DIRECTLY to WQ Brain (no local backtest).
# Field pool is sourced from `constants/data_fields_union_USA.json` filtered to
# delay=0 + type=MATRIX. The only universe carrying D0 fields is TOP1000.
#
# Generator goals (per public-repo evidence for passing WQ Brain submissions):
#   - turnover-controlling wrappers (trade_when / ts_decay_linear)
#   - SUBINDUSTRY-friendly cross-sectional ops at the outer layer
#   - rich field families beyond PV (option, analyst, news, sentiment, fundamental)
#   - avoid pathological structures (group_neutralize without GROUP fields, etc.)

import json
from pathlib import Path

# Field family weights — bias toward families with historically higher fitness.
# Calibrated from constants/d0_field_universe_matrix.json single-field probe:
# - fundamental + analyst: lowest TO (~0.01) → free for the budget
# - socialmedia: highest checks-passed (5/8) on a single field
# - news + raw pv: high TO or noise dominant → demote
# The adaptive loop reshapes these between rounds.
DEFAULT_FAMILY_WEIGHTS = {
    "fundamental": 0.25,  # 660 fields, ultra-low TO friendly
    "socialmedia": 0.20,  # 8 fields, sentiment/buzz; best single-field checks
    "analyst":     0.20,  # 24 fields, ultra-low TO, EPS/revenue
    "option":      0.20,  # 64 fields, volatility/IV
    "news":        0.05,  # 75 fields, but TO blows up
    "pv":          0.10,  # 21 fields incl. adjfactor noise — filtered below
}

# Drop non-signal PV fields (adjustment factors, static metadata).
PV_FIELD_BLOCKLIST = {
    "adjfactor", "sharesout", "top1000", "top200", "top2000", "top3000",
    "top500", "topsp500",
}

# Wrappers proven to control turnover in passing alphas.
D0_WRAPPERS = (
    "rank",
    "zscore",
    "winsorize_std4",          # winsorize(x, std=4)
    "decay_linear_8",          # ts_decay_linear(x, 8)
    "decay_linear_16",         # ts_decay_linear(x, 16)
    "trade_when_volgate",      # trade_when(volume > adv20 * 1.2, x, -1)
)

# D0 inner ops (depth > 0). Subset of WQ Brain FASTEXPR with WIDE applicability.
# WQ Brain D0 verified-rejected ops (this account's FASTEXPR surface):
#   ts_returns, s_log_1p -> "inaccessible or unknown operator"
D0_TS_OPS_1ARG = (
    "ts_rank", "ts_zscore", "ts_mean", "ts_std_dev",
    "ts_delta", "ts_decay_linear",
    "ts_arg_max", "ts_arg_min", "ts_sum",
)
D0_TS_OPS_2ARG = ("ts_corr",)
# `divide` is a major source of CONCENTRATED_WEIGHT failures (extreme
# denominator -> single-name blowup). Keep it but weight it down by
# repeating the safer arithmetic ops in the choice pool.
D0_ARITH_OPS = ("add", "subtract", "multiply", "multiply",
                "subtract", "divide")
# NOTE: s_log_1p is in the canonical catalog but WQ Brain rejects it at sim
# time as "inaccessible or unknown operator" on this account. Removed.
D0_ELEMWISE_UNARY = ("log", "abs", "sign")

D0_WINDOWS = (3, 5, 10, 20, 40, 60, 120)


def load_d0_field_pool(union_path: str | Path) -> dict[str, list[str]]:
    """Group D0 MATRIX fields by category. Returns {family: [field_id,...]}.

    Excludes VECTOR (need vec_* wrappers, handled separately) and
    GROUP/UNIVERSE/SYMBOL types (not usable as expression leaves directly).
    """
    fields = json.load(open(union_path))
    pool: dict[str, list[str]] = {}
    for f in fields:
        if f.get("delay") != 0 or f.get("type") != "MATRIX":
            continue
        cat = f["category"]["id"]
        fid = f["id"]
        if cat == "pv" and fid in PV_FIELD_BLOCKLIST:
            continue
        pool.setdefault(cat, []).append(fid)
    return pool


def _d0_leaf(rng: random.Random, pool: dict[str, list[str]],
             weights: dict[str, float]) -> str:
    """Sample one D0 field, weighted by family."""
    families = [fam for fam in weights if fam in pool and pool[fam]]
    w = [weights[fam] for fam in families]
    fam = rng.choices(families, weights=w, k=1)[0]
    return rng.choice(pool[fam])


def _d0_inner(rng: random.Random, depth: int, pool, weights) -> str:
    """Generate the core expression (no outer wrapper). depth>=1."""
    if depth <= 0:
        return _d0_leaf(rng, pool, weights)
    r = rng.random()
    if r < 0.50:
        op = rng.choice(D0_TS_OPS_1ARG)
        inner = _d0_inner(rng, depth - 1, pool, weights)
        d = rng.choice(D0_WINDOWS)
        return f"{op}({inner}, {d})"
    if r < 0.62:
        op = rng.choice(D0_TS_OPS_2ARG)
        a = _d0_leaf(rng, pool, weights)
        b = _d0_leaf(rng, pool, weights)
        while a == b:
            b = _d0_leaf(rng, pool, weights)
        d = rng.choice(D0_WINDOWS)
        return f"{op}({a}, {b}, {d})"
    if r < 0.85:
        op = rng.choice(D0_ARITH_OPS)
        a = _d0_inner(rng, depth - 1, pool, weights)
        b = _d0_inner(rng, depth - 1, pool, weights)
        return f"{op}({a}, {b})"
    if r < 0.95:
        op = rng.choice(D0_ELEMWISE_UNARY)
        inner = _d0_inner(rng, depth - 1, pool, weights)
        return f"{op}({inner})"
    return _d0_leaf(rng, pool, weights)


def _apply_d0_wrapper(rng: random.Random, core: str, wrapper: str) -> str:
    """Always pre-winsorize the core to bound extreme single-name weights,
    then apply the chosen outer wrapper. This is what suppresses
    CONCENTRATED_WEIGHT failures from `divide`-heavy cores."""
    safe = f"winsorize({core}, std=4)"
    if wrapper == "rank":
        return f"rank({safe})"
    if wrapper == "zscore":
        return f"zscore({safe})"
    if wrapper == "winsorize_std4":
        return f"rank({safe})"  # winsorize-then-rank
    if wrapper == "decay_linear_8":
        return f"ts_decay_linear(rank({safe}), 8)"
    if wrapper == "decay_linear_16":
        return f"ts_decay_linear(rank({safe}), 16)"
    if wrapper == "trade_when_volgate":
        return f"trade_when(volume > adv20 * 1.2, rank({safe}), -1)"
    return f"rank({safe})"


def generate_d0(n: int, pool: dict[str, list[str]],
                seed: int = 31,
                max_depth: int = 4,
                min_depth: int = 2,
                family_weights: dict[str, float] | None = None,
                wrapper_weights: dict[str, float] | None = None) -> List[str]:
    """Generate n unique D0 expressions sampling from the D0 field pool.

    `pool` must come from load_d0_field_pool(...).
    `family_weights` and `wrapper_weights` let the adaptive loop reshape
    sampling without touching the generator code.
    """
    rng = random.Random(seed)
    fweights = family_weights or DEFAULT_FAMILY_WEIGHTS
    if wrapper_weights:
        wraps = list(wrapper_weights.keys())
        wws = [wrapper_weights[k] for k in wraps]
    else:
        wraps = list(D0_WRAPPERS)
        wws = [1.0] * len(wraps)

    seen: set[str] = set()
    out: List[str] = []
    tries = 0
    while len(out) < n and tries < n * 50:
        tries += 1
        depth = rng.randint(min_depth, max_depth)
        core = _d0_inner(rng, depth, pool, fweights)
        wrapper = rng.choices(wraps, weights=wws, k=1)[0]
        expr = _apply_d0_wrapper(rng, core, wrapper)
        h = hashlib.md5(expr.encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append(expr)
    return out


if __name__ == "__main__":
    for e in generate(10, seed=1):
        print(e)
