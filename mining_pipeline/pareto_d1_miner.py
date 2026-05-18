"""Pareto-guided D1 alpha miner.

Different from prior miners (smart/obscure/combo/lean) which generate
candidates from a fixed template. This module is iterative:

  1. Load *all* prior simulation results into a unified history.
  2. Sign-normalize (if SH < 0, treat as the candidate that would result
     from a -1 multiplier - flip sharpe and returns, keep turnover, take
     absolute value of fitness).
  3. Compute Pareto frontier on (Sharpe, Fitness) under turnover
     constraint TO in [0.01, 0.7].
  4. For each Pareto point, propose K variations:
     - smoothing  (ts_mean wrap with window in {3, 5, 10})
     - hump       (default-threshold hump wrap)
     - pair combo (rank-add with another Pareto point)
     - setting    (decay perturbation)
  5. Submit, ingest, recompute Pareto, loop until budget exhausted.

The strategy is a discrete analogue of SGD: each iteration we step in
the direction of the dominant marginal-improvement axis (turnover-down
when fitness is the bottleneck, sharpe-up when sharpe is).

Run:
    python -m mining_pipeline.pareto_d1_miner --iter 3 --variants 5
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pareto-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

PRIOR_FILES = [
    "WQ_D1_SCAN.json",
    "WQ_D1_REFINED.json",
    "WQ_D1_OBSCURE.json",
    "WQ_D1_COMBO.json",
    "WQ_D1_LEAN.json",
    "WQ_D1_LEAN_FOLLOWUP.json",
    "WQ_D1_PARETO.json",
]

BASE_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "delay":          1,
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
    "pasteurization": "ON",
    "universe":       "TOP3000",
    "neutralization": "INDUSTRY",
    "decay":          8,
    "truncation":     0.05,
}

POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 6
TO_LO, TO_HI = 0.01, 0.7
SH_BAR, FIT_BAR = 1.25, 1.0


# -----------------------------------------------------------------------
# History ingest
# -----------------------------------------------------------------------

@dataclass
class HistEntry:
    expression: str
    settings: dict
    sharpe: float
    turnover: float
    fitness: float
    returns: float
    all_checks_pass: bool
    alpha_id: str
    source: str
    # sign-normalized view (sharpe and fitness always >= 0)
    eff_expression: str = ""
    eff_sharpe: float = 0.0
    eff_fitness: float = 0.0


def load_history() -> list[HistEntry]:
    out: list[HistEntry] = []
    for fname in PRIOR_FILES:
        p = REPO / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception as e:
            log.warning(f"skip {fname}: {e}")
            continue
        for r in data:
            if not r.get("ok"):
                continue
            sh = float(r.get("sharpe", 0))
            to = float(r.get("turnover", 0))
            fit = float(r.get("fitness", 0))
            ret = float(r.get("returns", 0))
            if not (TO_LO <= to <= TO_HI):
                continue
            entry = HistEntry(
                expression=r.get("expression", ""),
                settings=r.get("settings", {}),
                sharpe=sh, turnover=to, fitness=fit, returns=ret,
                all_checks_pass=bool(r.get("all_checks_pass", False)),
                alpha_id=r.get("alpha_id", ""),
                source=fname,
            )
            # sign-normalize: if SH < 0, flipped form would have eff_sh = -sh
            if sh < 0:
                entry.eff_expression = f"-1 * ({entry.expression})"
                entry.eff_sharpe = -sh
                entry.eff_fitness = -fit  # fit follows sign of sharpe
            else:
                entry.eff_expression = entry.expression
                entry.eff_sharpe = sh
                entry.eff_fitness = fit
            out.append(entry)
    # de-dup by eff_expression keeping the one with best SH
    by_expr: dict[str, HistEntry] = {}
    for e in out:
        cur = by_expr.get(e.eff_expression)
        if cur is None or e.eff_sharpe > cur.eff_sharpe:
            by_expr[e.eff_expression] = e
    return list(by_expr.values())


# -----------------------------------------------------------------------
# Pareto frontier
# -----------------------------------------------------------------------

def pareto_frontier(entries: list[HistEntry]) -> list[HistEntry]:
    """Non-dominated set on (eff_sharpe, eff_fitness). Higher is better
    on both axes."""
    out: list[HistEntry] = []
    for e in entries:
        dominated = False
        for o in entries:
            if o is e:
                continue
            if (o.eff_sharpe >= e.eff_sharpe and
                o.eff_fitness >= e.eff_fitness and
                (o.eff_sharpe > e.eff_sharpe or o.eff_fitness > e.eff_fitness)):
                dominated = True
                break
        if not dominated:
            out.append(e)
    out.sort(key=lambda x: -x.eff_sharpe)
    return out


# -----------------------------------------------------------------------
# Variation generation
# -----------------------------------------------------------------------

def propose_variations(point: HistEntry, frontier: list[HistEntry],
                       rng: random.Random) -> list[tuple[str, str, dict]]:
    """For one Pareto point, return [(tag, expression, settings), ...]
    proposals biased toward closing the gap to the (SH>=1.25, FIT>=1.0)
    target zone.

    - If FIT < FIT_BAR : reduce TO with smoothing wrappers or higher decay
    - If SH  < SH_BAR  : try pair combos (variance reduction)
    - If both above bar: still try combos to push margin higher
    """
    out: list[tuple[str, str, dict]] = []
    expr = point.eff_expression
    s = dict(BASE_SETTINGS)
    s.update(point.settings)
    # always force D1
    s["delay"] = 1
    s["region"] = "USA"

    fit_gap = FIT_BAR - point.eff_fitness
    sh_gap  = SH_BAR - point.eff_sharpe

    # 1. Smoothing wraps - reduce TO to lift fitness
    if fit_gap > 0 or point.turnover > 0.15:
        for w in (3, 5, 10):
            wrapped = f"rank(ts_mean(({expr}), {w}))"
            out.append((f"smooth{w}", wrapped, s))

    # 2. Setting variants - higher decay also cuts TO
    if fit_gap > 0:
        for d in (16, 32):
            sv = dict(s); sv["decay"] = d
            out.append((f"decay{d}", expr, sv))

    # 3. Pair combos with another Pareto point
    if frontier:
        partners = [p for p in frontier if p is not point]
        rng.shuffle(partners)
        for partner in partners[:2]:
            combo = f"rank(({expr}) + ({partner.eff_expression}))"
            out.append((f"combo_{partner.alpha_id[:6]}", combo, s))

    # 4. Hump (low-pass)
    if fit_gap > 0:
        out.append(("hump", f"rank(hump(({expr})))", s))

    return out


# -----------------------------------------------------------------------
# WQ Brain submission
# -----------------------------------------------------------------------

@dataclass
class SimResult:
    ok: bool
    expression: str
    settings: dict
    tag: str = ""
    parent_alpha: str = ""
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    checks: list = field(default_factory=list)
    checks_passed: int = 0
    checks_total: int = 0
    all_checks_pass: bool = False
    alpha_id: str = ""
    error: str = ""


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def submit(session, expression: str, settings: dict) -> SimResult:
    body = {"type": "REGULAR", "settings": settings, "regular": expression}
    for attempt in range(5):
        try:
            r = session.post("https://api.worldquantbrain.com/simulations",
                             json=body, timeout=30)
        except Exception as e:
            log.info(f"   POST exc: {e}; sleep 10"); time.sleep(10); continue
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            time.sleep(wait); continue
        break
    if r.status_code != 201:
        return SimResult(ok=False, expression=expression, settings=settings,
                         error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return SimResult(ok=False, expression=expression, settings=settings,
                         error="no Location header")

    t0 = time.time()
    last_status = ""
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        try:
            rp = session.get(progress_url, timeout=30)
        except Exception:
            continue
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st != last_status:
            log.info(f"   status={st} ({int(time.time()-t0)}s)")
            last_status = st
        if st == "COMPLETE":
            aid = data.get("alpha")
            try:
                ra = session.get(
                    f"https://api.worldquantbrain.com/alphas/{aid}",
                    timeout=30)
            except Exception as e:
                return SimResult(ok=False, expression=expression,
                                 settings=settings, alpha_id=aid or "",
                                 error=f"alpha-get-exc: {e}")
            if ra.status_code != 200:
                return SimResult(ok=False, expression=expression,
                                 settings=settings, alpha_id=aid or "",
                                 error=f"alpha-get-{ra.status_code}")
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            passed = [c for c in checks if c.get("result") == "PASS"]
            failed = [c for c in checks if c.get("result") == "FAIL"]
            return SimResult(
                ok=True, expression=expression, settings=settings,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                checks=checks, checks_passed=len(passed),
                checks_total=len(checks),
                all_checks_pass=(len(failed) == 0 and len(checks) > 0),
                alpha_id=aid or "")
        if st in ("ERROR", "FAILED", "WARNING"):
            return SimResult(ok=False, expression=expression, settings=settings,
                             error=f"sim-{st}: {data.get('message','')[:300]}")
    return SimResult(ok=False, expression=expression, settings=settings,
                     error="poll-timeout")


# -----------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iter", type=int, default=3)
    ap.add_argument("--variants", type=int, default=5,
                    help="proposals per Pareto point per iteration")
    ap.add_argument("--top-pareto", type=int, default=4,
                    help="cap how many Pareto points we expand per iter")
    ap.add_argument("--out", type=str, default="WQ_D1_PARETO.json")
    ap.add_argument("--seed", type=int, default=37)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    rng = random.Random(args.seed)
    out_path = REPO / args.out
    all_results: list[SimResult] = []
    if out_path.exists():
        try:
            all_results = [SimResult(**{k: v for k, v in d.items()
                                        if k in SimResult.__annotations__})
                           for d in json.loads(out_path.read_text())]
            log.info(f"   resumed {len(all_results)} prior pareto results")
        except Exception:
            pass

    for it in range(1, args.iter + 1):
        history = load_history()
        log.info(f"=== iter {it}/{args.iter}: history has {len(history)} dedup entries")

        frontier = pareto_frontier(history)[:args.top_pareto]
        log.info(f"   Pareto frontier ({len(frontier)} points):")
        for f in frontier:
            log.info(f"     SH={f.eff_sharpe:+.2f}  FIT={f.eff_fitness:+.2f}  "
                     f"TO={f.turnover:.3f}  src={f.source}  "
                     f"alpha={f.alpha_id}")

        # propose variations from each Pareto point
        proposals: list[tuple[str, str, dict, str]] = []
        for f in frontier:
            v = propose_variations(f, frontier, rng)
            rng.shuffle(v)
            for tag, expr, s in v[:args.variants]:
                proposals.append((tag, expr, s, f.alpha_id))
        log.info(f"   {len(proposals)} proposals queued for iter {it}")

        for i, (tag, expr, s, parent_aid) in enumerate(proposals, 1):
            log.info(f"--- iter{it}.{i}/{len(proposals)}  [{tag}]  parent={parent_aid}")
            log.info(f"   expr: {expr[:160]}")
            r = submit(cm.session, expr, s)
            r.tag = tag
            r.parent_alpha = parent_aid
            if r.ok:
                log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                         f"pass={r.all_checks_pass} ({r.checks_passed}/{r.checks_total}) "
                         f"alpha={r.alpha_id}")
            else:
                log.info(f"   ERR: {r.error[:160]}")
            all_results.append(r)
            out_path.write_text(json.dumps([asdict(x) for x in all_results], indent=2))

    # final summary
    ok = [r for r in all_results if r.ok]
    ready = [r for r in ok if r.all_checks_pass]
    print()
    print("=" * 110)
    print(f"pareto done after {args.iter} iters: {len(ok)}/{len(all_results)} OK, "
          f"submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    print("Top results:")
    for r in ok[:15]:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}] {r.expression[:60]}")
    print("=" * 110)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
