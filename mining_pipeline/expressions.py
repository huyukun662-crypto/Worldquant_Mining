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
import json
import random
from pathlib import Path
from typing import List, Tuple

# Field pool — spans all 8 WQ data categories (analyst, fundamental,
# model, news, option, pv, sentiment, socialmedia) per user spec. Loaded
# from `constants/field_pool_USA_TOP3000.json` (built by
# `scripts/build_field_pool.py`). Falls back to PV-only if the file is
# missing.
_POOL_PATH = Path(__file__).resolve().parent.parent / "constants" / "field_pool_USA_TOP3000.json"
_BLACKLIST_PATH = Path(__file__).resolve().parent.parent / "constants" / "field_blacklist.json"
_PV_BASELINE = ("close", "open", "high", "low", "volume", "vwap", "returns",
                "cap", "sharesout", "adv20")


def _load_blacklist() -> set[str]:
    if _BLACKLIST_PATH.exists():
        return set(json.loads(_BLACKLIST_PATH.read_text()))
    return set()


def _build_pool() -> tuple[dict[str, list[str]], tuple[str, ...], tuple[str, ...]]:
    """Load the curated pool and filter out blacklisted fields. Categories
    that go empty are dropped."""
    if _POOL_PATH.exists():
        raw: dict[str, list[str]] = json.loads(_POOL_PATH.read_text())
    else:
        raw = {"pv": list(_PV_BASELINE)}
    bl = _load_blacklist()
    pool = {c: [f for f in fs if f not in bl] for c, fs in raw.items()}
    pool = {c: fs for c, fs in pool.items() if fs}
    fields = tuple(f for cat in pool.values() for f in cat)
    cats = tuple(pool.keys())
    return pool, fields, cats


_POOL, FIELDS, CATEGORIES = _build_pool()


def reload_pool() -> tuple[int, int]:
    """Re-read pool + blacklist from disk. Returns (n_fields, n_categories)."""
    global _POOL, FIELDS, CATEGORIES
    _POOL, FIELDS, CATEGORIES = _build_pool()
    return len(FIELDS), len(CATEGORIES)

TS_OPS_1ARG = ("ts_zscore", "ts_rank", "ts_delta", "ts_mean",
               "ts_std_dev", "ts_returns", "ts_decay_linear")
TS_OPS_2ARG = ("ts_corr",)  # both args time-series; share a window

CS_OPS = ("rank", "zscore", "scale", "normalize")  # wrappers
ARITH_OPS = ("add", "subtract", "multiply", "divide")
ELEMWISE_UNARY = ("log", "abs", "reverse", "sign")  # s_log_1p inaccessible on this account

WINDOWS_DEFAULT = (3, 5, 10, 20, 40, 60)


def _leaf(rng: random.Random) -> str:
    # Sample category first, then field — this gives each category equal
    # representation regardless of how many fields it contributes to the
    # pool. Without this, model (30 fields) would dominate sentiment (10).
    cat = rng.choice(CATEGORIES)
    return rng.choice(_POOL[cat])


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


if __name__ == "__main__":
    for e in generate(10, seed=1):
        print(e)
