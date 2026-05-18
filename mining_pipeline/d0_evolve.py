"""Pareto-front evolutionary search for a submittable D0 alpha.

Strategy
--------
1. Maintain an archive (list of `WQResult`) of every COMPLETE simulation.
2. Score each candidate scalarly:
       score = fitness + 0.5*sharpe + 0.1*(checks_passed/checks_total)
               - 5.0 * max(0, turnover - 0.25)
3. Each generation:
   - Pick top-K parents by score AND the Pareto front on
     (sharpe, fitness, -turnover, checks_passed).
   - Spawn `M` mutants per parent (mutation operators below).
   - Spawn `R` fresh random expressions.
   - Submit all to WQ, add results to archive.
   - If any candidate passes the full Submit gate, return it immediately.

Mutation operators (each fires with its own probability):
- swap_field    : replace a leaf field with another from the pool
- swap_op       : replace a ts_* op with another of same arity
- swap_window   : ± 1 step in WINDOWS
- swap_wrap     : replace outer cs wrap
- flip_sign     : prepend `multiply(-1, ...)`
- swap_setting  : perturb one entry in the current setting dict
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import List, Tuple

# ---- D0 hard constraints (per user spec 2026-05-18) -----------------------
# delay=0; SH>=2.0; FIT>=1.3; PV-only fields; decay 1-5; truncation 0.005-0.02.
PV_FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns",
             "cap", "adv20", "sharesout")

TS_OPS_1ARG = (
    "ts_mean", "ts_std_dev", "ts_zscore", "ts_rank", "ts_delta",
    "ts_decay_linear", "ts_arg_max", "ts_arg_min", "ts_quantile",
    "ts_av_diff", "ts_scale", "ts_product",
)
TS_OPS_2ARG = ("ts_corr", "ts_covariance")
CS_WRAPS = ("rank", "zscore", "winsorize", "normalize", "quantile", "scale")
UNARY = ("hump", "signed_power", "abs", "sign")
WINDOWS = (3, 5, 10, 20, 30, 60, 120)

SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000", "TOP500"],
    "delay":          [0],
    "decay":          [1, 2, 3, 4, 5],
    "truncation":     [0.005, 0.01, 0.015, 0.02],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR"],
    "pasteurization": ["ON"],
}

SHARPE_FLOOR = 2.0
FITNESS_FLOOR = 1.3
TURNOVER_CEILING = 0.25

# C01-style structural seeds (PV-only, known-good D0 templates).
# `ts_decay_exp_window` is not in this account's operator catalog
# (verified against constants/upstream_operatorRAW.json); ts_decay_linear
# is used as the closest substitute.
SEED_EXPRS = (
    # C01: mean-reversion on intraday VWAP gap
    "ts_decay_linear(rank(divide(subtract(vwap, close), close)), 4)",
    "ts_decay_linear(rank(divide(subtract(vwap, close), close)), 3)",
    "ts_decay_linear(rank(divide(subtract(vwap, close), close)), 5)",
    # 1-day reversal on returns
    "rank(multiply(-1, returns))",
    "ts_decay_linear(rank(multiply(-1, returns)), 4)",
    # Short-window close mean-reversion
    "ts_decay_linear(rank(multiply(-1, ts_delta(close, 1))), 3)",
    "ts_decay_linear(rank(multiply(-1, ts_delta(close, 5))), 4)",
    # Volume-price correlation (illiquidity premium variant)
    "rank(multiply(-1, ts_corr(close, volume, 20)))",
    # VWAP - mid-price reversion
    "ts_decay_linear(rank(divide(subtract(vwap, divide(add(high, low), 2)), close)), 4)",
    # Intraday range relative to close
    "rank(divide(subtract(high, low), close))",
    # ADV-relative size momentum
    "rank(divide(volume, adv20))",
    "ts_decay_linear(rank(divide(volume, adv20)), 4)",
)


def fields_pool() -> List[str]:
    return list(PV_FIELDS)


# ---------- expression generation & mutation -------------------------------

def _rand_window(rng: random.Random) -> int:
    return rng.choice(WINDOWS)


def random_expr(rng: random.Random) -> str:
    fields = fields_pool()
    r = rng.random()
    if r < 0.55:
        op = rng.choice(TS_OPS_1ARG)
        return _wrap(rng, f"{op}({rng.choice(fields)}, {_rand_window(rng)})")
    if r < 0.80:
        op = rng.choice(TS_OPS_2ARG)
        a, b = rng.sample(fields, 2)
        return _wrap(rng, f"{op}({a}, {b}, {_rand_window(rng)})")
    # nested
    inner_op = rng.choice(TS_OPS_1ARG)
    outer_op = rng.choice(TS_OPS_1ARG)
    f = rng.choice(fields)
    return _wrap(rng,
                 f"{outer_op}({inner_op}({f}, {_rand_window(rng)}), {_rand_window(rng)})")


def _wrap(rng: random.Random, core: str) -> str:
    w = rng.choice(CS_WRAPS)
    if w == "winsorize":
        return f"winsorize({core}, std=4)"
    if w == "quantile":
        return f"quantile({core}, driver=\"gaussian\")"
    return f"{w}({core})"


# Mutation helpers --------------------------------------------------------

_FIELD_RE = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in PV_FIELDS) + r"|[a-z][a-z0-9_]{2,})\b"
)


def _swap_field(expr: str, rng: random.Random) -> str:
    fields = fields_pool()
    # Find all field-like tokens; only replace ones that ARE in our pool
    tokens = list(_FIELD_RE.finditer(expr))
    candidates = [m for m in tokens if m.group(1) in fields]
    if not candidates:
        return expr
    m = rng.choice(candidates)
    new = rng.choice(fields)
    return expr[:m.start()] + new + expr[m.end():]


def _swap_op(expr: str, rng: random.Random) -> str:
    # Replace a ts_* op of compatible arity
    for arity_pool in (TS_OPS_1ARG, TS_OPS_2ARG):
        positions = [(m.start(), m.end()) for op in arity_pool
                     for m in re.finditer(rf"\b{re.escape(op)}\b", expr)]
        if positions and rng.random() < 0.5:
            s, e = rng.choice(positions)
            new = rng.choice(arity_pool)
            return expr[:s] + new + expr[e:]
    return expr


def _swap_window(expr: str, rng: random.Random) -> str:
    # Pick a standalone integer literal and bump it ± 1 step
    matches = []
    for m in re.finditer(r"(?<![A-Za-z0-9_])(\d+)(?![A-Za-z0-9_.])", expr):
        try:
            val = int(m.group(1))
        except ValueError:
            continue
        if val in WINDOWS:
            matches.append(m)
    if not matches:
        return expr
    m = rng.choice(matches)
    val = int(m.group(1))
    idx = WINDOWS.index(val)
    new_idx = max(0, min(len(WINDOWS) - 1, idx + rng.choice((-1, 1))))
    new_val = WINDOWS[new_idx]
    return expr[:m.start()] + str(new_val) + expr[m.end():]


def _swap_wrap(expr: str, rng: random.Random) -> str:
    # Strip outermost CS_WRAPS call and replace
    for w in CS_WRAPS:
        prefix_simple = f"{w}("
        if expr.startswith(prefix_simple):
            inner = expr[len(prefix_simple):-1]
            # If wrap has trailing args (winsorize, quantile) strip them
            if w == "winsorize":
                inner = re.sub(r",\s*std=\d+\)?$", "", inner)
            elif w == "quantile":
                inner = re.sub(r",\s*driver=\"gaussian\"\)?$", "", inner)
            if inner.endswith(")"):
                inner = inner
            new = rng.choice([c for c in CS_WRAPS if c != w])
            return _wrap(rng, inner)
    return expr


def _flip_sign(expr: str, _: random.Random) -> str:
    if expr.startswith("multiply(-1, "):
        # already negated; remove
        return expr[len("multiply(-1, "):-1]
    return f"multiply(-1, {expr})"


MUTATIONS = (
    ("swap_field",   _swap_field,   0.45),
    ("swap_op",      _swap_op,      0.25),
    ("swap_window",  _swap_window,  0.20),
    ("swap_wrap",    _swap_wrap,    0.10),
    ("flip_sign",    _flip_sign,    0.15),
)


def mutate(expr: str, rng: random.Random, max_muts: int = 2) -> str:
    out = expr
    applied = 0
    for _, fn, p in MUTATIONS:
        if rng.random() < p:
            out = fn(out, rng)
            applied += 1
            if applied >= max_muts:
                break
    if out == expr:
        # forced single mutation
        _, fn, _ = rng.choice(MUTATIONS)
        out = fn(out, rng)
    return out


def mutate_settings(parent_settings: dict, rng: random.Random) -> dict:
    s = dict(parent_settings)
    # Drop fields not in our search space
    s = {k: s.get(k, SETTING_SPACE[k][0]) for k in SETTING_SPACE}
    # Perturb one or two keys
    keys = list(SETTING_SPACE.keys())
    for k in rng.sample(keys, k=rng.randint(1, 2)):
        s[k] = rng.choice(SETTING_SPACE[k])
    s["delay"] = 0   # fixed D0
    s["pasteurization"] = "ON"
    return s


def random_settings(rng: random.Random) -> dict:
    return {k: rng.choice(v) for k, v in SETTING_SPACE.items()}


# ---------- Pareto + scoring -----------------------------------------------

@dataclass
class Cand:
    expression: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 1.0
    fitness: float = -10.0
    checks_passed: int = 0
    checks_total: int = 0
    alpha_id: str = ""
    ok: bool = False
    error: str = ""

    @property
    def check_ratio(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 0.0

    @property
    def score(self) -> float:
        if not self.ok:
            return -100.0
        return (self.fitness
                + 0.5 * self.sharpe
                + 0.1 * self.check_ratio
                - 5.0 * max(0.0, self.turnover - 0.25))

    @property
    def passes_submit_gate(self) -> bool:
        return (self.ok
                and self.sharpe >= SHARPE_FLOOR
                and self.turnover < TURNOVER_CEILING
                and self.fitness >= FITNESS_FLOOR
                and self.checks_total > 0
                and self.checks_passed == self.checks_total)


def pareto_front(cands: List[Cand]) -> List[Cand]:
    """Pareto on (sharpe↑, fitness↑, -turnover↑, check_ratio↑)."""
    pts = [(c.sharpe, c.fitness, -c.turnover, c.check_ratio) for c in cands]
    keep: List[Cand] = []
    for i, ci in enumerate(cands):
        dominated = False
        for j, cj in enumerate(cands):
            if i == j or not cj.ok:
                continue
            pj = pts[j]; pi = pts[i]
            if all(pj[k] >= pi[k] for k in range(4)) and any(pj[k] > pi[k] for k in range(4)):
                dominated = True; break
        if not dominated and ci.ok:
            keep.append(ci)
    return keep


def select_parents(archive: List[Cand], k: int, rng: random.Random) -> List[Cand]:
    pf = pareto_front(archive)
    pf.sort(key=lambda c: c.score, reverse=True)
    # Top-K from Pareto front; if shorter than k, fill from the rest by score
    if len(pf) >= k:
        return pf[:k]
    rest = sorted([c for c in archive if c.ok and c not in pf],
                  key=lambda c: c.score, reverse=True)
    return pf + rest[:k - len(pf)]


def dedup(exprs: List[str]) -> List[str]:
    seen = set(); out = []
    for e in exprs:
        h = hashlib.md5(e.encode()).hexdigest()
        if h in seen: continue
        seen.add(h); out.append(e)
    return out
