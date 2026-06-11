"""WorldQuant 5-Agent mining workflow.

A structured, 5-stage ("5-agent") pipeline for mining *submittable*
delay-1 (D1) alphas on WorldQuant Brain, biased toward **low turnover**
and **low max-drawdown**, while deliberately **avoiding IV (implied
volatility) fields**.

The five cooperating agents:

    1. DataFieldAgent   -- curates the D1 field universe. PV-only by
                           construction; asserts NO implied-volatility /
                           option-derived ("IV") fields leak in.
    2. IdeaAgent        -- generates fresh, low-turnover-biased alpha
                           hypotheses from scratch (slow operators + long
                           lookbacks). NEVER reuses Alpha101 / classical
                           templates (per CLAUDE.md spec).
    3. ConstructionAgent-- materializes each idea into a FASTEXPR string +
                           a D1 simulation settings body. Emphasizes the
                           strongest low-turnover lever: signal `decay`.
    4. SimulationAgent  -- submits to WQ Brain `/simulations` (concurrent,
                           account-safe), polls, and collects the
                           authoritative IS metrics incl. `drawdown`.
    5. ValidationAgent  -- scores submittability (WQ `is.checks`), enforces
                           low-turnover + low-drawdown + Sharpe gates, and
                           ranks survivors.

The authoritative numbers come from WQ Brain (see CLAUDE.md "Backtest
authority"). There is no local backtest here -- WQ is the evaluator.

Run:
    python -m mining_pipeline.agent_workflow --ideas 12 --refine 3 \
        --universe TOP3000 --out WQ_5AGENT_REPORT.json
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import importlib.util
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field as dc_field, asdict
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("5agent")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
BASE = "https://api.worldquantbrain.com"


# ---------------------------------------------------------------------------
# Agent 1: DataFieldAgent -- D1 field universe, IV-free
# ---------------------------------------------------------------------------

# Curated price-volume fields exposed on this account at delay=1 (verified
# against constants/data_fields_union_USA.json). These are the ONLY fields
# the IdeaAgent may use. They are all PV / market fields -- none are
# implied-volatility or option-derived.
PV_FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns",
             "cap", "sharesout", "adv20")

# Substrings that mark a field as implied-volatility / option-derived. The
# user requirement is "avoid IV fields"; DataFieldAgent hard-blocks any
# field id matching these so no IV signal can ever enter an expression.
IV_BLOCKLIST = ("implied", "ivol", "_iv", "iv_", "impvol", "optvol",
                "option", "vega", "gamma_", "vix")


class DataFieldAgent:
    """Curates and guards the field universe."""

    def __init__(self, fields=PV_FIELDS):
        self.fields = tuple(self._guard(fields))

    @staticmethod
    def _is_iv(name: str) -> bool:
        low = name.lower()
        return any(tok in low for tok in IV_BLOCKLIST)

    def _guard(self, fields):
        clean = [f for f in fields if not self._is_iv(f)]
        dropped = [f for f in fields if self._is_iv(f)]
        if dropped:
            log.warning(f"[DataFieldAgent] dropped IV fields: {dropped}")
        log.info(f"[DataFieldAgent] D1 universe = {len(clean)} PV fields "
                 f"(IV-free): {clean}")
        return clean

    def assert_iv_free(self, expression: str) -> None:
        if self._is_iv(expression):
            raise ValueError(f"IV field leaked into expression: {expression}")


# ---------------------------------------------------------------------------
# Agent 2: IdeaAgent -- low-turnover alpha hypotheses (fresh, no templates)
# ---------------------------------------------------------------------------

# Slow time-series operators: applied over LONG windows they produce
# slow-moving signals -> intrinsically low turnover. We deliberately omit
# short-window ts_delta / ts_returns which spike turnover.
SLOW_TS = ("ts_mean", "ts_decay_linear", "ts_zscore", "ts_rank", "ts_std_dev")
LONG_WINDOWS = (20, 30, 40, 60, 90, 120)
WRAPPERS = ("rank", "zscore", "normalize")          # cross-sectional scale
ARITH = ("subtract", "divide", "add")
UNARY = ("reverse", "log", "s_log_1p")              # incl. sign-flip (reverse)


class IdeaAgent:
    """Generates fresh low-turnover-biased expressions from scratch."""

    def __init__(self, dfa: DataFieldAgent, seed: int = 0):
        self.dfa = dfa
        self.rng = random.Random(seed)

    def _slow(self, fld: str) -> str:
        op = self.rng.choice(SLOW_TS)
        w = self.rng.choice(LONG_WINDOWS)
        return f"{op}({fld}, {w})"

    def _core(self) -> str:
        f = self.rng
        flds = self.dfa.fields
        r = f.random()
        if r < 0.40:
            # single slow signal, optionally sign-flipped (mean-reversion)
            s = self._slow(f.choice(flds))
            if f.random() < 0.5:
                s = f"reverse({s})"
            return s
        if r < 0.72:
            # ratio / spread of two slow signals (e.g. trend vs level)
            a = self._slow(f.choice(flds))
            b = self._slow(f.choice(flds))
            return f"{f.choice(ARITH)}({a}, {b})"
        # smoothed signal: decay-linear over another slow signal -> very low TO
        inner = self._slow(f.choice(flds))
        w = f.choice(LONG_WINDOWS)
        return f"ts_decay_linear({inner}, {w})"

    def generate_one(self) -> str:
        core = self._core()
        if self.rng.random() < 0.25:
            core = f"{self.rng.choice(UNARY)}({core})"
        expr = f"{self.rng.choice(WRAPPERS)}({core})"
        self.dfa.assert_iv_free(expr)
        return expr

    def generate(self, n: int) -> list[str]:
        out, seen = [], set()
        guard = 0
        while len(out) < n and guard < n * 50:
            guard += 1
            e = self.generate_one()
            h = hashlib.md5(e.encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            out.append(e)
        log.info(f"[IdeaAgent] generated {len(out)} low-turnover ideas")
        return out


# ---------------------------------------------------------------------------
# Agent 3: ConstructionAgent -- D1 settings, low-turnover lever = decay
# ---------------------------------------------------------------------------

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
    "delay":          1,        # D1 (account has no delay-0 access)
    "pasteurization": "ON",
}


class ConstructionAgent:
    """Builds (expression, settings) simulation bodies for D1."""

    def __init__(self, universe: str = "TOP3000"):
        self.universe = universe

    def default_settings(self) -> dict:
        # High decay + INDUSTRY neutralization -> strong low-turnover prior.
        s = dict(FIXED_SETTINGS)
        s.update(universe=self.universe, decay=32, truncation=0.08,
                 neutralization="INDUSTRY")
        return s

    def refine_grid(self) -> list[dict]:
        """Setting variants for the refinement pass, all biased low-TO."""
        grid = []
        for decay in (16, 32, 64):
            for neut in ("INDUSTRY", "SUBINDUSTRY", "MARKET"):
                s = dict(FIXED_SETTINGS)
                s.update(universe=self.universe, decay=decay,
                         truncation=0.08, neutralization=neut)
                grid.append(s)
        return grid


# ---------------------------------------------------------------------------
# Agent 4: SimulationAgent -- concurrent WQ Brain /simulations
# ---------------------------------------------------------------------------

@dataclass
class SimResult:
    ok: bool
    expression: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    margin: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    fail_checks: list = dc_field(default_factory=list)
    alpha_id: str = ""
    error: str = ""


class SimulationAgent:
    """Submits/polls WQ Brain simulations, account-safe concurrency."""

    def __init__(self, session, max_concurrent: int = 1,
                 poll_timeout_s: int = 600, poll_interval_s: int = 6):
        self.session = session
        self.sem = threading.Semaphore(max_concurrent)
        self.poll_timeout_s = poll_timeout_s
        self.poll_interval_s = poll_interval_s

    def _submit_one(self, expression: str, settings: dict) -> SimResult:
        body = {"type": "REGULAR", "settings": settings, "regular": expression}
        # POST with patient 429 backoff. This credential is shared, so the
        # account's concurrent-simulation slots are often momentarily busy
        # (HTTP 429 CONCURRENT_SIMULATION_LIMIT_EXCEEDED). Slots free up in
        # ~1 min, so we wait persistently (up to ~20 min) rather than drop
        # the job.
        r = None
        for attempt in range(48):
            r = self.session.post(f"{BASE}/simulations", json=body, timeout=30)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After") or 25)
                if attempt % 4 == 0:
                    log.info(f"   429 (slot busy); waiting {wait:.0f}s "
                             f"[attempt {attempt+1}]")
                time.sleep(wait)
                continue
            break
        if r is None or r.status_code != 201:
            return SimResult(False, expression, settings,
                             error=f"submit-{getattr(r,'status_code','?')}: "
                                   f"{getattr(r,'text','')[:200]}")
        progress = r.headers.get("Location")
        if not progress:
            return SimResult(False, expression, settings,
                             error="no Location header")
        t0 = time.time()
        while time.time() - t0 < self.poll_timeout_s:
            time.sleep(self.poll_interval_s)
            rp = self.session.get(progress, timeout=30)
            if rp.status_code == 429:
                time.sleep(20); continue
            if rp.status_code != 200:
                continue
            data = rp.json()
            st = data.get("status", "")
            if st == "COMPLETE":
                return self._fetch_alpha(data.get("alpha"), expression, settings)
            if st in ("ERROR", "FAILED"):
                return SimResult(False, expression, settings,
                                 error=f"sim-{st}: {data.get('message','')[:200]}")
        return SimResult(False, expression, settings, error="poll-timeout")

    def _fetch_alpha(self, alpha_id, expression, settings) -> SimResult:
        ra = self.session.get(f"{BASE}/alphas/{alpha_id}", timeout=30)
        if ra.status_code != 200:
            return SimResult(False, expression, settings, alpha_id=alpha_id or "",
                             error=f"alpha-get-{ra.status_code}")
        isb = ra.json().get("is") or {}
        checks = isb.get("checks") or []
        fails = [c.get("name") for c in checks if c.get("result") == "FAIL"]
        return SimResult(
            ok=True, expression=expression, settings=settings,
            sharpe=float(isb.get("sharpe") or 0.0),
            turnover=float(isb.get("turnover") or 0.0),
            fitness=float(isb.get("fitness") or 0.0),
            returns=float(isb.get("returns") or 0.0),
            drawdown=float(isb.get("drawdown") or 0.0),
            margin=float(isb.get("margin") or 0.0),
            longCount=int(isb.get("longCount") or 0),
            shortCount=int(isb.get("shortCount") or 0),
            checks_passed=sum(1 for c in checks if c.get("result") == "PASS"),
            checks_total=len(checks),
            fail_checks=fails,
            alpha_id=alpha_id or "",
        )

    def run(self, jobs: list[tuple[str, dict]]) -> list[SimResult]:
        """Run (expression, settings) jobs concurrently (semaphore-bounded)."""
        results: list[SimResult] = [None] * len(jobs)  # type: ignore

        def worker(i, expr, st):
            with self.sem:
                log.info(f"   [sim {i+1}/{len(jobs)}] decay={st.get('decay')} "
                         f"neut={st.get('neutralization')} expr={expr[:70]}")
                res = self._submit_one(expr, st)
                tag = "OK " if res.ok else "ERR"
                if res.ok:
                    log.info(f"   [{tag} {i+1}] SH={res.sharpe:+.3f} "
                             f"TO={res.turnover:.3f} DD={res.drawdown:.3f} "
                             f"FIT={res.fitness:+.3f} "
                             f"checks={res.checks_passed}/{res.checks_total}")
                else:
                    log.info(f"   [{tag} {i+1}] {res.error[:90]}")
                results[i] = res

        with cf.ThreadPoolExecutor(max_workers=self.sem._value + 2) as ex:
            futs = [ex.submit(worker, i, e, s) for i, (e, s) in enumerate(jobs)]
            for f in cf.as_completed(futs):
                f.result()
        return results


# ---------------------------------------------------------------------------
# Agent 5: ValidationAgent -- submittable + low-TO + low-DD gates & ranking
# ---------------------------------------------------------------------------

# WQ Brain official + user thresholds.
SHARPE_FLOOR   = 1.25
TURNOVER_CEIL  = 0.25
TURNOVER_FLOOR = 0.01     # below this WQ flags LOW_TURNOVER
DRAWDOWN_CEIL  = 0.50     # "low maxdd" target

# Auto-fail checks that block submission (SELF_CORRELATION is PENDING until
# competition close, so it does not count as a hard fail here).
HARD_FAIL_CHECKS = {"LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER",
                    "HIGH_TURNOVER", "CONCENTRATED_WEIGHT",
                    "LOW_SUB_UNIVERSE_SHARPE", "UNITS", "MATCHES_COMPETITION"}


class ValidationAgent:
    """Gates and ranks results for submittability + low TO + low DD."""

    @staticmethod
    def submittable(r: SimResult) -> bool:
        if not r.ok:
            return False
        if r.sharpe <= SHARPE_FLOOR:
            return False
        if not (TURNOVER_FLOOR < r.turnover < TURNOVER_CEIL):
            return False
        if r.drawdown > DRAWDOWN_CEIL:
            return False
        if any(c in HARD_FAIL_CHECKS for c in r.fail_checks):
            return False
        return True

    @staticmethod
    def score(r: SimResult) -> float:
        """Composite: reward Sharpe & fitness, penalize turnover & drawdown.
        Used to RANK submittable survivors (lower TO / DD float to the top)."""
        return (r.fitness
                + 0.5 * r.sharpe
                - 4.0 * r.turnover      # push turnover down
                - 2.0 * r.drawdown)     # push max-drawdown down

    def select(self, results: list[SimResult]) -> list[SimResult]:
        survivors = [r for r in results if self.submittable(r)]
        survivors.sort(key=self.score, reverse=True)
        log.info(f"[ValidationAgent] {len(survivors)} submittable survivors "
                 f"(SH>{SHARPE_FLOOR}, {TURNOVER_FLOOR}<TO<{TURNOVER_CEIL}, "
                 f"DD<{DRAWDOWN_CEIL}, no hard-fail checks)")
        return survivors


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ideas", type=int, default=12,
                    help="Number of low-turnover ideas to screen (1 sim each)")
    ap.add_argument("--refine", type=int, default=3,
                    help="Top-K ideas to refine over the settings grid")
    ap.add_argument("--universe", type=str, default="TOP3000")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--concurrent", type=int, default=1)
    ap.add_argument("--out", type=str, default="WQ_5AGENT_REPORT.json")
    args = ap.parse_args()

    cm = _load(VENDOR / "core" / "credential_manager.py", "cm")
    mgr = cm.CredentialManager(base_path=str(REPO))
    if not mgr.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {mgr.credentials.username}")

    # --- wire the 5 agents -------------------------------------------------
    dfa = DataFieldAgent()
    idea = IdeaAgent(dfa, seed=args.seed)
    con = ConstructionAgent(universe=args.universe)
    sim = SimulationAgent(mgr.session, max_concurrent=args.concurrent)
    val = ValidationAgent()

    all_results: list[SimResult] = []

    def persist():
        with open(args.out, "w") as f:
            json.dump([asdict(r) for r in all_results if r is not None],
                      f, indent=2)

    # --- Stage 1+2+3: ideas -> default D1 body -----------------------------
    ideas = idea.generate(args.ideas)
    for e in ideas:
        log.info(f"   idea: {e}")
    screen_jobs = [(e, con.default_settings()) for e in ideas]

    # --- Stage 4: screening simulations ------------------------------------
    log.info(f"=== SCREEN: {len(screen_jobs)} simulations "
             f"(~{len(screen_jobs)*120/args.concurrent/60:.0f} min) ===")
    screen = sim.run(screen_jobs)
    all_results.extend(screen); persist()

    # --- Stage 5 (interim) + refine the most promising ---------------------
    ok = [r for r in screen if r.ok]
    # promising = positive Sharpe & turnover already in band; rank by score
    promising = [r for r in ok
                 if r.sharpe > 0 and TURNOVER_FLOOR < r.turnover < TURNOVER_CEIL]
    promising.sort(key=val.score, reverse=True)
    refine_exprs = [r.expression for r in promising[:args.refine]]
    log.info(f"=== refining top {len(refine_exprs)} ideas over settings grid ===")
    refine_jobs = [(e, s) for e in refine_exprs for s in con.refine_grid()]
    if refine_jobs:
        log.info(f"=== REFINE: {len(refine_jobs)} simulations "
                 f"(~{len(refine_jobs)*120/args.concurrent/60:.0f} min) ===")
        refine = sim.run(refine_jobs)
        all_results.extend(refine); persist()

    # --- Stage 5: validate & rank ------------------------------------------
    survivors = val.select(all_results)
    persist()

    print()
    print("=" * 116)
    print(f"5-AGENT WORKFLOW  account={mgr.credentials.username}  universe={args.universe}  delay=1")
    print(f"total sims: {sum(1 for r in all_results if r and r.ok)} OK / "
          f"{len([r for r in all_results if r])}   submittable survivors: {len(survivors)}")
    print("-" * 116)
    print(f"{'SH':>6}{'TO':>7}{'DD':>7}{'FIT':>7}{'ret':>7}  {'checks':>7}  "
          f"{'decay':>5} {'neut':<12} alpha_id    expression")
    for r in survivors[:25]:
        s = r.settings
        print(f"{r.sharpe:6.2f}{r.turnover:7.3f}{r.drawdown:7.3f}"
              f"{r.fitness:7.2f}{r.returns:7.3f}  {r.checks_passed}/{r.checks_total:<5}  "
              f"{s.get('decay')!s:>5} {s.get('neutralization'):<12} "
              f"{r.alpha_id:<10} {r.expression[:60]}")
    print("=" * 116)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
