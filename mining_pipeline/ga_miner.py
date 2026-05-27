"""Genetic-algorithm D0 factor miner for WorldQuant Brain.

Per CLAUDE.md the local backtest does not generalize, so this miner uses WQ
Brain `/simulations` as the canonical evaluator (`--evaluator wq`). A local
proxy (`--evaluator local`) is provided ONLY to smoke-test GA mechanics
offline; its numbers are advisory.

Design choices driven by the user's spec:

* **D0 only** - every simulation runs at `delay=0`. delay is NOT part of the
  evolvable settings (it is pinned in `Genome.full_settings`).
* **No template reuse** - genomes are typed expression trees grown from
  scratch (operators x PV fields). No Alpha101 / classical factors.
* **No IV fields** - `FIELDS` is price/volume/fundamental only; implied-
  volatility / option fields are deliberately excluded.
* **Simple** - `max_ops` (default 6) and `max_depth` (default 4) keep the
  evolved expressions short.
* **Genetic algorithm** - tournament selection + elitism + subtree crossover
  + point/field/window/subtree/settings mutation. (Not Optuna/Bayes.)

Fitness rewards a *submittable* alpha: high IS Sharpe and fitness, turnover
inside the band, and all WQ IS checks passing (incl. LOW_SUB_UNIVERSE_SHARPE).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .wq_client import (WQClient, SimResult, settings_key, BiometricRequired,
                        FIXED_SETTINGS)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ga-miner")

REPO = Path(__file__).resolve().parent.parent

# --- building blocks -------------------------------------------------------
# D0-appropriate price/volume/fundamental fields. NO implied-volatility / option
# fields (user spec: "不要IV相关字段").
FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns",
          "adv20", "cap")

TS1 = ("ts_mean", "ts_std_dev", "ts_zscore", "ts_rank", "ts_delta",
       "ts_decay_linear", "ts_returns", "ts_delay", "ts_min", "ts_max")
TS2 = ("ts_corr",)
ARITH = ("add", "subtract", "multiply", "divide")
UNARY = ("rank", "zscore", "normalize", "log", "abs", "sign", "s_log_1p",
         "reverse")
CS_UNARY = ("rank", "zscore", "normalize")  # good final wrappers

WMIN, WMAX = 2, 60

# Evolvable simulation settings. delay is intentionally absent (pinned to 0).
SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000"],
    "decay":          [0, 4, 8],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"],
    "truncation":     [0.01, 0.08],
}


# --- expression tree -------------------------------------------------------
@dataclass
class Node:
    kind: str                     # field | unary | ts1 | ts2 | arith
    op: str = ""
    field_name: str = ""
    window: int = 0
    children: list = field(default_factory=list)

    def render(self) -> str:
        if self.kind == "field":
            return self.field_name
        if self.kind == "unary":
            return f"{self.op}({self.children[0].render()})"
        if self.kind == "ts1":
            return f"{self.op}({self.children[0].render()}, {self.window})"
        if self.kind == "ts2":
            return (f"{self.op}({self.children[0].render()}, "
                    f"{self.children[1].render()}, {self.window})")
        if self.kind == "arith":
            return (f"{self.op}({self.children[0].render()}, "
                    f"{self.children[1].render()})")
        raise ValueError(self.kind)

    def copy(self) -> "Node":
        return Node(self.kind, self.op, self.field_name, self.window,
                    [c.copy() for c in self.children])

    def walk(self) -> list["Node"]:
        out = [self]
        for c in self.children:
            out.extend(c.walk())
        return out

    def op_count(self) -> int:
        return sum(1 for n in self.walk() if n.kind != "field")

    def depth(self) -> int:
        if not self.children:
            return 1
        return 1 + max(c.depth() for c in self.children)


def _leaf(rng: random.Random) -> Node:
    return Node("field", field_name=rng.choice(FIELDS))


def _rand_window(rng: random.Random) -> int:
    return rng.randint(WMIN, WMAX)


def random_tree(rng: random.Random, max_depth: int) -> Node:
    """Grow a random expression tree, biased toward time-series structure."""
    if max_depth <= 1:
        return _leaf(rng)
    r = rng.random()
    if r < 0.45:                                  # ts1
        op = rng.choice(TS1)
        return Node("ts1", op=op, window=_rand_window(rng),
                    children=[random_tree(rng, max_depth - 1)])
    if r < 0.60:                                  # ts2 (corr)
        return Node("ts2", op=rng.choice(TS2), window=_rand_window(rng),
                    children=[random_tree(rng, max_depth - 1),
                              random_tree(rng, max_depth - 1)])
    if r < 0.80:                                  # arith
        return Node("arith", op=rng.choice(ARITH),
                    children=[random_tree(rng, max_depth - 1),
                              random_tree(rng, max_depth - 1)])
    if r < 0.92:                                  # unary transform
        return Node("unary", op=rng.choice(UNARY),
                    children=[random_tree(rng, max_depth - 1)])
    return _leaf(rng)


# --- genome ----------------------------------------------------------------
@dataclass
class Genome:
    tree: Node
    settings: dict
    sim: Optional[SimResult] = None
    score: float = -1e9

    def expression(self) -> str:
        return self.tree.render()

    def full_settings(self) -> dict:
        s = {"delay": 0}                          # D0: pinned
        s.update(self.settings)
        return s

    def key(self) -> str:
        return f"{self.expression()}||{settings_key(self.full_settings())}"

    def copy(self) -> "Genome":
        return Genome(self.tree.copy(), dict(self.settings))


def random_settings(rng: random.Random) -> dict:
    return {k: rng.choice(v) for k, v in SETTING_SPACE.items()}


def random_genome(rng: random.Random, max_depth: int, max_ops: int) -> Genome:
    for _ in range(40):
        t = random_tree(rng, max_depth)
        # ~60% of the time make sure the signal is cross-sectionally scaled
        if t.kind not in ("unary",) and rng.random() < 0.6:
            t = Node("unary", op=rng.choice(CS_UNARY), children=[t])
        if t.kind == "field":
            continue                              # reject bare-field alphas
        if 1 <= t.op_count() <= max_ops and t.depth() <= max_depth + 1:
            return Genome(t, random_settings(rng))
    # fallback: a minimal valid alpha
    t = Node("unary", op="rank",
             children=[Node("ts1", op="ts_delta", window=rng.randint(2, 20),
                            children=[_leaf(rng)])])
    return Genome(t, random_settings(rng))


# --- genetic operators -----------------------------------------------------
def mutate(g: Genome, rng: random.Random, max_depth: int, max_ops: int) -> Genome:
    child = g.copy()
    kind = rng.choices(
        ["point", "field", "window", "subtree", "settings"],
        weights=[0.25, 0.2, 0.2, 0.2, 0.15])[0]
    nodes = child.tree.walk()

    if kind == "settings":
        k = rng.choice(list(SETTING_SPACE))
        child.settings[k] = rng.choice(SETTING_SPACE[k])
        return child
    if kind == "field":
        leaves = [n for n in nodes if n.kind == "field"]
        if leaves:
            rng.choice(leaves).field_name = rng.choice(FIELDS)
        return child
    if kind == "window":
        tss = [n for n in nodes if n.kind in ("ts1", "ts2")]
        if tss:
            n = rng.choice(tss)
            n.window = max(WMIN, min(WMAX, n.window + rng.choice(
                [-20, -10, -5, -3, -1, 1, 3, 5, 10, 20])))
        return child
    if kind == "point":
        cands = [n for n in nodes if n.kind != "field"]
        if cands:
            n = rng.choice(cands)
            pool = {"unary": UNARY, "ts1": TS1, "ts2": TS2, "arith": ARITH}[n.kind]
            n.op = rng.choice(pool)
        return child
    # subtree replacement
    target = rng.choice(nodes)
    repl = random_tree(rng, max(2, max_depth - 1))
    target.kind, target.op = repl.kind, repl.op
    target.field_name, target.window = repl.field_name, repl.window
    target.children = repl.children
    # enforce bounds, else bail to a fresh genome
    if child.tree.op_count() > max_ops or child.tree.depth() > max_depth + 1:
        return random_genome(rng, max_depth, max_ops)
    return child


def crossover(a: Genome, b: Genome, rng: random.Random,
              max_depth: int, max_ops: int) -> Genome:
    child = a.copy()
    nodes = child.tree.walk()
    target = rng.choice(nodes)
    donor = rng.choice(b.tree.walk()).copy()
    target.kind, target.op = donor.kind, donor.op
    target.field_name, target.window = donor.field_name, donor.window
    target.children = donor.children
    # uniform settings crossover
    for k in SETTING_SPACE:
        if rng.random() < 0.5:
            child.settings[k] = b.settings[k]
    if (child.tree.kind == "field" or child.tree.op_count() > max_ops
            or child.tree.op_count() < 1 or child.tree.depth() > max_depth + 1):
        return random_genome(rng, max_depth, max_ops)
    return child


def tournament(pop: list[Genome], rng: random.Random, k: int) -> Genome:
    return max(rng.sample(pop, min(k, len(pop))), key=lambda g: g.score)


# --- fitness ---------------------------------------------------------------
def fitness(sim: SimResult, turnover_ceiling: float) -> float:
    if sim is None or not sim.ok:
        return -10.0
    to = sim.turnover
    if to <= 0.01 or to >= 0.7:        # outside WQ's hard turnover band
        return -5.0 + 0.1 * sim.sharpe
    score = sim.sharpe + 0.4 * sim.fitness
    if to > turnover_ceiling:
        score -= 3.0 * (to - turnover_ceiling)
    if sim.checks_total:
        score += 0.5 * (sim.checks_passed / sim.checks_total)
    return score


# --- local proxy evaluator (offline smoke test only) ----------------------
class LocalClient:
    """Mirror of WQClient.evaluate_many using the yfinance proxy backtest.

    Numbers DO NOT generalize (see CLAUDE.md); used only to verify GA
    mechanics without WQ Brain auth.
    """

    def __init__(self, base_path="."):
        from .data import load
        from .evaluator import Evaluator
        self.panel = load()
        self.ev = Evaluator(self.panel)
        self.is_mask = self.panel.is_mask()

    def authenticate(self, *a, **k):
        log.info("local evaluator: no auth needed")

    def evaluate_many(self, jobs, use_cache=True):
        from .backtest import backtest
        out: dict[str, SimResult] = {}
        for expr, settings in jobs:
            key = f"{expr}||{settings_key(settings)}"
            if key in out:
                continue
            try:
                sig = self.ev.evaluate(expr)
                bt = backtest(sig, self.panel.returns, self.is_mask)
                out[key] = SimResult(ok=True, expression=expr, settings=settings,
                                     sharpe=bt.sharpe, turnover=bt.turnover,
                                     returns=bt.annual_return)
            except Exception as e:
                out[key] = SimResult(ok=False, expression=expr,
                                     settings=settings, error=str(e)[:140])
        return out


# --- GA loop ---------------------------------------------------------------
def run_ga(client, args) -> dict:
    rng = random.Random(args.seed)
    pop: list[Genome] = []
    seen_exprs: set[str] = set()
    while len(pop) < args.pop:
        g = random_genome(rng, args.max_depth, args.max_ops)
        e = g.expression()
        if e in seen_exprs:
            continue
        seen_exprs.add(e)
        pop.append(g)

    survivors: dict[str, dict] = {}
    history = []

    for gen in range(args.gens):
        jobs = [(g.expression(), g.full_settings()) for g in pop]
        log.info(f"=== gen {gen+1}/{args.gens}: evaluating {len(jobs)} genomes ===")
        results = client.evaluate_many(jobs)
        for g in pop:
            g.sim = results.get(g.key())
            g.score = fitness(g.sim, args.turnover_ceiling)
        pop.sort(key=lambda g: g.score, reverse=True)

        for g in pop:
            if g.sim and g.sim.passes_submit(args.turnover_ceiling):
                survivors[g.key()] = _record(g)

        best = pop[0]
        bs = best.sim
        log.info(f"   best score={best.score:.3f} "
                 f"SH={bs.sharpe:+.3f} TO={bs.turnover:.3f} FIT={bs.fitness:+.3f} "
                 f"checks={bs.checks_passed}/{bs.checks_total} "
                 f"| submittable so far: {len(survivors)}")
        log.info(f"   best expr: {best.expression()}  settings={best.settings}")
        history.append({"gen": gen + 1, "best_score": best.score,
                        "best_sharpe": bs.sharpe, "best_expr": best.expression(),
                        "n_survivors": len(survivors)})
        _save(args.out, survivors, history, pop, args.turnover_ceiling)

        if gen == args.gens - 1:
            break

        # next generation
        elites = [g.copy() for g in pop[:args.elite]]
        nxt = elites
        guard = 0
        next_exprs = {g.expression() for g in elites}
        while len(nxt) < args.pop and guard < args.pop * 50:
            guard += 1
            if rng.random() < args.cx:
                child = crossover(tournament(pop, rng, args.tournament),
                                  tournament(pop, rng, args.tournament),
                                  rng, args.max_depth, args.max_ops)
            else:
                child = tournament(pop, rng, args.tournament).copy()
            if rng.random() < args.mut:
                child = mutate(child, rng, args.max_depth, args.max_ops)
            e = child.expression()
            if e in next_exprs:
                continue
            next_exprs.add(e)
            child.sim = None
            child.score = -1e9
            nxt.append(child)
        pop = nxt

    return {"survivors": survivors, "history": history}


def _record(g: Genome) -> dict:
    s = g.sim
    return {"expression": g.expression(), "settings": g.full_settings(),
            "sharpe": s.sharpe, "turnover": s.turnover, "fitness": s.fitness,
            "returns": s.returns, "drawdown": s.drawdown,
            "sub_universe_sharpe": s.sub_universe_sharpe,
            "op_count": s.op_count, "alpha_id": s.alpha_id,
            "checks_passed": s.checks_passed, "checks_total": s.checks_total}


def _save(out, survivors, history, pop, tc):
    ranked = sorted(survivors.values(), key=lambda r: r["sharpe"], reverse=True)
    payload = {"survivors": ranked, "history": history,
               "turnover_ceiling": tc,
               "best_current": [{"expr": g.expression(), "score": g.score,
                                 "sharpe": g.sim.sharpe if g.sim else None,
                                 "turnover": g.sim.turnover if g.sim else None}
                                for g in pop[:10] if g.sim]}
    Path(out).write_text(json.dumps(payload, indent=2))


def main():
    ap = argparse.ArgumentParser(description="GA D0 factor miner for WQ Brain")
    ap.add_argument("--evaluator", choices=["wq", "local"], default="wq")
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--gens", type=int, default=8)
    ap.add_argument("--elite", type=int, default=4)
    ap.add_argument("--tournament", type=int, default=3)
    ap.add_argument("--cx", type=float, default=0.6, help="crossover rate")
    ap.add_argument("--mut", type=float, default=0.4, help="mutation rate")
    ap.add_argument("--max-depth", type=int, default=4)
    ap.add_argument("--max-ops", type=int, default=6)
    ap.add_argument("--turnover-ceiling", type=float, default=0.25)
    ap.add_argument("--max-concurrent", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=str, default="GA_MINING_REPORT.json")
    args = ap.parse_args()

    if args.evaluator == "local":
        client = LocalClient(base_path=str(REPO))
    else:
        client = WQClient(base_path=str(REPO), max_concurrent=args.max_concurrent)
        try:
            client.authenticate()
        except BiometricRequired as e:
            log.error(str(e))
            return 3

    res = run_ga(client, args)
    surv = sorted(res["survivors"].values(), key=lambda r: r["sharpe"],
                  reverse=True)
    print("\n" + "=" * 100)
    print(f"SUBMITTABLE survivors (all IS checks PASS, TO < "
          f"{args.turnover_ceiling}): {len(surv)}")
    print(f"{'SH':>7}{'TO':>7}{'FIT':>7}{'subSH':>7}{'ops':>5}  "
          f"alpha_id   universe  neut  expression")
    for r in surv[:25]:
        s = r["settings"]
        print(f"{r['sharpe']:7.3f}{r['turnover']:7.3f}{r['fitness']:7.3f}"
              f"{r['sub_universe_sharpe']:7.3f}{r['op_count']:5d}  "
              f"{r['alpha_id']:<10} {s.get('universe'):<9} "
              f"{s.get('neutralization'):<12} {r['expression'][:70]}")
    print("=" * 100)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
