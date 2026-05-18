"""D0 rare-operator × rare-field expression generator.

Generates expressions that:
- use only D0-available rare fields (from `d0_fields.flat_rare`)
- prefer rare WQ FASTEXPR operators (not the standard rank/zscore/ts_mean
  family used by `expressions.py`)
- stay shallow (1-2 fields per expression) to maximise the chance of
  passing WQ Submit-Alpha checks (LOW_TURNOVER, SUB_UNIVERSE, ...)

No local evaluation — these strings are submitted directly to WQ Brain.
"""

from __future__ import annotations

import hashlib
import random
from typing import List

from .d0_fields import flat_rare

# Rare WQ FASTEXPR ops that are present in this account's catalog
# (verified against constants/upstream_operatorRAW.json: ts_kurtosis,
# ts_skewness, ts_co_*, ts_partial_corr are NOT exposed).
TS_RARE_1ARG = (
    "ts_arg_max", "ts_arg_min", "ts_quantile", "ts_av_diff",
    "ts_scale", "ts_product", "ts_zscore",
)
TS_RARE_2ARG = ("ts_corr", "ts_covariance")
UNARY_RARE = ("hump", "signed_power")

# Cross-sectional wrappers, picking less-common ones first.
CS_WRAPS = ("winsorize", "normalize", "quantile", "rank")

WINDOWS = (5, 10, 20, 40, 60, 120)


def _ts_unary(rng: random.Random, fields: List[str]) -> str:
    op = rng.choice(TS_RARE_1ARG)
    f = rng.choice(fields)
    d = rng.choice(WINDOWS)
    return f"{op}({f}, {d})"


def _ts_binary(rng: random.Random, fields: List[str]) -> str:
    op = rng.choice(TS_RARE_2ARG)
    a = rng.choice(fields)
    b = rng.choice(fields)
    while b == a:
        b = rng.choice(fields)
    d = rng.choice(WINDOWS)
    return f"{op}({a}, {b}, {d})"


def _unary_xform(rng: random.Random, inner: str) -> str:
    op = rng.choice(UNARY_RARE)
    if op == "hump":
        return f"hump({inner}, 0.01)"
    if op == "signed_power":
        return f"signed_power({inner}, 0.5)"
    return f"{op}({inner})"


def _core(rng: random.Random, fields: List[str]) -> str:
    base = _ts_binary(rng, fields) if rng.random() < 0.35 else _ts_unary(rng, fields)
    if rng.random() < 0.35:
        base = _unary_xform(rng, base)
    return base


def _wrap(rng: random.Random, core: str) -> str:
    w = rng.choice(CS_WRAPS)
    if w == "winsorize":
        return f"winsorize({core}, std=4)"
    if w == "quantile":
        return f"quantile({core}, driver=\"gaussian\")"
    return f"{w}({core})"


def generate_one(rng: random.Random, fields: List[str]) -> str:
    return _wrap(rng, _core(rng, fields))


def generate(n: int, seed: int = 11, universe: str = "TOP3000",
             max_alpha_count: int = 50, per_cat: int = 30) -> List[str]:
    rng = random.Random(seed)
    fields = flat_rare(universe=universe, max_alpha_count=max_alpha_count,
                       per_cat=per_cat, seed=seed)
    if not fields:
        raise RuntimeError("rare-field pool empty; loosen max_alpha_count")
    seen = set()
    out: List[str] = []
    tries = 0
    while len(out) < n and tries < n * 50:
        tries += 1
        e = generate_one(rng, fields)
        h = hashlib.md5(e.encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append(e)
    return out


if __name__ == "__main__":
    for e in generate(10, seed=1):
        print(e)
