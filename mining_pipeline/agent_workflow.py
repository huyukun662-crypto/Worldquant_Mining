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

import requests

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
UNARY = ("reverse", "log")                          # incl. sign-flip (reverse)


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

    # -- economically-grounded low-turnover priors -------------------------
    #
    # Per the user's "smarter idea generation" directive: build fresh
    # expressions around documented low-turnover PV anomaly *structures*
    # (long-term reversal, skip-recent momentum, low-volatility, price-vs-MA
    # trend, illiquidity). These are constructed from operators here -- NOT
    # imported from worldquant_mining.factor_templates / Alpha101. Each is
    # emitted in BOTH signs (sign-fitting): WQ Brain decides which direction
    # actually carries Sharpe. Long horizons => intrinsically low turnover.

    def _prior_families(self) -> list[tuple[str, str]]:
        """Return (name, expression) for each economically-motivated prior,
        sign UN-fixed (the natural/long direction). Windows sampled long."""
        f = self.rng
        W = lambda *c: f.choice(c)
        fams: list[tuple[str, str]] = []

        # 1. Long-term reversal / momentum: average daily return over a long
        #    window (= cumulative drift). Natural sign = momentum; reverse =
        #    reversal. Uses the `returns` field + ts_mean (both proven-valid).
        fams.append(("ltr_ret",  f"rank(ts_mean(returns, {W(120, 180, 250)}))"))

        # 2. Skip-recent (12-1) momentum: long-window drift minus recent drift.
        wl, ws = W(200, 250), W(20, 40)
        fams.append(("mom_skip",
                     f"rank(subtract(ts_mean(returns, {wl}), "
                     f"ts_mean(returns, {ws})))"))

        # 3. Low-volatility anomaly: low realized-vol names outperform
        #    (natural sign of vol is +; reverse() longs the low-vol book).
        fams.append(("lowvol",   f"rank(ts_std_dev(returns, {W(40, 60, 120)}))"))

        # 4. Price-vs-long-MA trend (rank is shift-invariant, so the ratio
        #    alone captures "above/below its long moving average").
        fams.append(("trend_ma",
                     f"rank(divide(close, ts_mean(close, {W(60, 120, 200)})))"))

        # 5. Volatility-scaled momentum (Sharpe-like): drift normalized by risk.
        fams.append(("volscaled_mom",
                     f"rank(divide(ts_mean(returns, {W(120, 200)}), "
                     f"ts_std_dev(returns, {W(40, 60)})))"))

        # 6. Volume-trend reversal: short vs long average turnover.
        wl, ws = W(60, 120), W(10, 20)
        fams.append(("vol_trend",
                     f"rank(subtract(ts_mean(volume, {ws}), "
                     f"ts_mean(volume, {wl})))"))

        # 7. Range-position: where price sits in its long high-low band.
        w = W(60, 120)
        fams.append(("range_pos",
                     f"rank(divide(subtract(close, ts_mean(low, {w})), "
                     f"subtract(ts_mean(high, {w}), ts_mean(low, {w}))))"))

        # 8. Liquidity/size tilt: small, illiquid names (cap proxy) -- low TO.
        fams.append(("size_tilt", f"rank(ts_mean(cap, {W(60, 120)}))"))

        return fams

    def generate_priors(self, n: int) -> list[str]:
        """Generate up to `n` low-turnover prior expressions, each in BOTH
        signs for sign-fitting. Returns a de-duplicated list."""
        out, seen = [], set()
        guard = 0
        while len(out) < n and guard < 200:
            guard += 1
            for _name, base in self._prior_families():
                for expr in (base, f"reverse({base})"):
                    self.dfa.assert_iv_free(expr)
                    h = hashlib.md5(expr.encode()).hexdigest()
                    if h in seen:
                        continue
                    seen.add(h)
                    out.append(expr)
                    if len(out) >= n:
                        break
                if len(out) >= n:
                    break
        log.info(f"[IdeaAgent] generated {len(out)} prior-based ideas "
                 f"(anomaly structures, both signs)")
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
        # Light decay preserves the (already slow, low-turnover) anomaly
        # signal while INDUSTRY neutralization removes sector beta. High
        # decay washed signal out in the random run, so screen light.
        s = dict(FIXED_SETTINGS)
        s.update(universe=self.universe, decay=6, truncation=0.08,
                 neutralization="INDUSTRY")
        return s

    def refine_grid(self) -> list[dict]:
        """Setting variants for the refinement pass. Explores the
        decay/turnover trade-off (low decay = more signal, higher TO;
        high decay = lower TO) and neutralization."""
        grid = []
        for decay in (0, 12, 32):
            for neut in ("INDUSTRY", "SUBINDUSTRY"):
                s = dict(FIXED_SETTINGS)
                s.update(universe=self.universe, decay=decay,
                         truncation=0.08, neutralization=neut)
                grid.append(s)
        return grid

    def best_settings(self) -> dict:
        """The decay/neutralization that won Stage-1 refine (volume-trend
        peak: decay=12, SUBINDUSTRY)."""
        s = dict(FIXED_SETTINGS)
        s.update(universe=self.universe, decay=12, truncation=0.08,
                 neutralization="SUBINDUSTRY")
        return s


# ---------------------------------------------------------------------------
# Stage-2: window-tuning + volume x price composites (push for SH > 1.25)
# ---------------------------------------------------------------------------
#
# Stage-1 found volume-trend = rank(subtract(ts_mean(volume,S), ts_mean(volume,L)))
# as the strongest low-turnover signal (+1.10). To cross the 1.25 bar we
# (a) tune the (S, L) windows and (b) DIVERSIFY it by adding orthogonal,
# already-positive-Sharpe PRICE signals -- a volume signal + a price signal
# should de-correlate and lift Sharpe. All signals are combined in their
# profitable (positive-Sharpe) direction, equal-weighted as ranks, re-ranked.

def stage2_phase_a() -> list[str]:
    """Window-tuned volume-trend singles + volume x price composites,
    all evaluated at the Stage-1-best setting (decay=12, SUBINDUSTRY)."""
    vt = lambda s, l: f"subtract(ts_mean(volume, {s}), ts_mean(volume, {l}))"

    # positive-Sharpe direction of each Stage-1 signal, as a rank in [0,1]:
    VT   = f"rank({vt(10, 120)})"                                  # +1.10
    RP   = ("reverse(rank(divide(subtract(close, ts_mean(low, 60)), "
            "subtract(ts_mean(high, 60), ts_mean(low, 60)))))")    # +1.00
    MA   = "reverse(rank(divide(close, ts_mean(close, 60))))"      # +0.56
    MOM  = "rank(subtract(ts_mean(returns, 200), ts_mean(returns, 40)))"  # +0.94

    exprs: list[str] = []

    # (a) window tuning of the volume-trend single (skip 10/120, already known)
    for s, l in [(5, 60), (5, 120), (5, 250), (10, 60),
                 (10, 250), (20, 120), (20, 250), (20, 60)]:
        exprs.append(f"rank({vt(s, l)})")

    # (b) volume x price composites (equal-weight rank sum, re-ranked)
    exprs.append(f"rank(add({VT}, {RP}))")                 # vol + range-pos
    exprs.append(f"rank(add({VT}, {MA}))")                 # vol + MA-reversion
    exprs.append(f"rank(add({VT}, {MOM}))")                # vol + momentum
    exprs.append(f"rank(add(add({VT}, {RP}), {MA}))")      # vol + 2 price
    exprs.append(f"rank(add(multiply({VT}, 2), {RP}))")    # vol overweighted

    return exprs


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
        self.max_concurrent = max(int(max_concurrent), 1)
        self.sem = threading.Semaphore(self.max_concurrent)
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
            try:
                r = self.session.post(f"{BASE}/simulations", json=body, timeout=30)
            except requests.exceptions.RequestException as e:
                log.info(f"   POST network error ({type(e).__name__}); retrying")
                time.sleep(10); continue
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
            # Network hiccups during polling must NOT kill the job (a shared,
            # loaded account intermittently times out); swallow and retry.
            try:
                rp = self.session.get(progress, timeout=30)
            except requests.exceptions.RequestException:
                continue
            if rp.status_code == 429:
                time.sleep(20); continue
            if rp.status_code != 200:
                continue
            try:
                data = rp.json()
            except ValueError:
                continue
            st = data.get("status", "")
            if st == "COMPLETE":
                return self._fetch_alpha(data.get("alpha"), expression, settings)
            if st in ("ERROR", "FAILED"):
                return SimResult(False, expression, settings,
                                 error=f"sim-{st}: {data.get('message','')[:200]}")
        return SimResult(False, expression, settings, error="poll-timeout")

    def _fetch_alpha(self, alpha_id, expression, settings) -> SimResult:
        for _ in range(5):
            try:
                ra = self.session.get(f"{BASE}/alphas/{alpha_id}", timeout=30)
            except requests.exceptions.RequestException:
                time.sleep(5); continue
            if ra.status_code == 200:
                break
            time.sleep(5)
        else:
            return SimResult(False, expression, settings, alpha_id=alpha_id or "",
                             error="alpha-get-network")
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

    def run(self, jobs: list[tuple[str, dict]],
            on_result=None) -> list[SimResult]:
        """Run (expression, settings) jobs, semaphore-bounded.

        `on_result(i, res, results)` (optional) is invoked after each job
        completes so the caller can persist partial results -- a single
        job NEVER crashes the batch (its exception becomes an error result).
        Thread count == max_concurrent, so jobs run in submission order.
        """
        results: list[SimResult] = [None] * len(jobs)  # type: ignore
        lock = threading.Lock()

        def worker(i, expr, st):
            with self.sem:
                log.info(f"   [sim {i+1}/{len(jobs)}] decay={st.get('decay')} "
                         f"neut={st.get('neutralization')} expr={expr[:70]}")
                try:
                    res = self._submit_one(expr, st)
                except Exception as e:  # never let one job kill the batch
                    res = SimResult(False, expr, st,
                                    error=f"worker-exc: {type(e).__name__}: {e}")
            tag = "OK " if res.ok else "ERR"
            if res.ok:
                log.info(f"   [{tag} {i+1}] SH={res.sharpe:+.3f} "
                         f"TO={res.turnover:.3f} DD={res.drawdown:.3f} "
                         f"FIT={res.fitness:+.3f} "
                         f"checks={res.checks_passed}/{res.checks_total}")
            else:
                log.info(f"   [{tag} {i+1}] {res.error[:90]}")
            results[i] = res
            if on_result is not None:
                with lock:
                    try:
                        on_result(i, res, results)
                    except Exception:
                        pass

        with cf.ThreadPoolExecutor(max_workers=self.max_concurrent) as ex:
            futs = [ex.submit(worker, i, e, s) for i, (e, s) in enumerate(jobs)]
            for f in cf.as_completed(futs):
                f.result()  # worker swallows its own errors; this won't raise
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
    ap.add_argument("--ideas", type=int, default=16,
                    help="Number of ideas to screen (1 sim each)")
    ap.add_argument("--mode", choices=("priors", "random"), default="priors",
                    help="priors = economically-grounded anomaly structures "
                         "with sign-fitting; random = fresh random combos")
    ap.add_argument("--refine", type=int, default=3,
                    help="Top-K ideas to refine over the settings grid")
    ap.add_argument("--stage2", action="store_true",
                    help="Run window-tuning + volume x price composites "
                         "(push the Stage-1 volume-trend winner past SH>1.25)")
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

    all_results: list[SimResult] = []   # results from completed stages

    def persist(current=None):
        """Write completed-stage results plus the in-progress `current`
        array. Called after EVERY sim (via on_result) so a crash mid-stage
        never loses data."""
        rows = [asdict(r) for r in all_results if r is not None]
        if current:
            rows += [asdict(r) for r in current if r is not None]
        tmp = f"{args.out}.tmp"
        with open(tmp, "w") as f:
            json.dump(rows, f, indent=2)
        Path(tmp).replace(args.out)   # atomic swap

    def _cb(i, res, results):
        persist(results)

    # --- Stage 1+2+3: ideas -> default D1 body -----------------------------
    if args.stage2:
        ideas = stage2_phase_a()
        screen_settings = con.best_settings()
        for e in ideas:
            dfa.assert_iv_free(e)
    else:
        ideas = (idea.generate_priors(args.ideas) if args.mode == "priors"
                 else idea.generate(args.ideas))
        screen_settings = con.default_settings()
    for e in ideas:
        log.info(f"   idea: {e}")
    screen_jobs = [(e, screen_settings) for e in ideas]

    # --- Stage 4: screening simulations ------------------------------------
    log.info(f"=== SCREEN: {len(screen_jobs)} simulations "
             f"(~{len(screen_jobs)*120/args.concurrent/60:.0f} min) ===")
    screen = sim.run(screen_jobs, on_result=_cb)
    all_results.extend(screen); persist()

    # --- Stage 5 (interim) + refine the most promising ---------------------
    ok = [r for r in screen if r.ok]
    # promising = positive Sharpe & turnover already in band; rank by score
    promising = [r for r in ok
                 if r.sharpe > 0 and TURNOVER_FLOOR < r.turnover < TURNOVER_CEIL]
    promising.sort(key=val.score, reverse=True)
    # Stage-2 refines fewer (top 2) since each composite is already deep.
    refine_k = 2 if args.stage2 else args.refine
    refine_exprs = [r.expression for r in promising[:refine_k]]
    log.info(f"=== refining top {len(refine_exprs)} ideas over settings grid ===")
    refine_jobs = [(e, s) for e in refine_exprs for s in con.refine_grid()]
    if refine_jobs:
        log.info(f"=== REFINE: {len(refine_jobs)} simulations "
                 f"(~{len(refine_jobs)*120/args.concurrent/60:.0f} min) ===")
        refine = sim.run(refine_jobs, on_result=_cb)
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
