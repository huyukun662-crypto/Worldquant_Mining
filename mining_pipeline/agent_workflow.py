"""WorldQuant 5-agent mining workflow (delay=1, no-IV, submittable-oriented).

This module implements a five-stage ("5-agent") pipeline that mines D1
(delay=1) alphas on WorldQuant Brain, biased toward LOW TURNOVER and LOW
MAX DRAWDOWN, and filtered for SUBMITTABILITY (every non-PENDING IS check
must PASS). Per the project spec it does NOT reuse Alpha101 or the
classical-factor library in `worldquant_mining.factor_templates`; instead
the HypothesisAgent constructs original factor *archetypes* from generic
financial priors (value, quality, growth, leverage, reversal, low-vol, ...).

The five agents
---------------
1. FieldAgent      - curated, verified, NON-IV field universe (PV + a
                     curated set of fundamental6 fields). Implied-volatility
                     and the whole `option` category are excluded.
2. HypothesisAgent - emits original archetype constructors with a per-class
                     window range (slow fundamentals -> low turnover; short
                     reversal -> moderate turnover but higher Sharpe).
3. GeneratorAgent  - instantiates archetypes into a diverse POOL of concrete
                     FASTEXPR expressions.
4. SimulatorAgent  - ONE joint Optuna (TPE) study over {expression, sign,
                     expression windows, simulation settings}; each trial
                     submits one simulation to WQ Brain and reads back IS
                     metrics. TPE concentrates the sim budget on the most
                     promising (expression, settings) regions.
5. ValidatorAgent  - applies the submittability gate + user constraints
                     (turnover < 0.25, low drawdown), ranks, writes report.

Submittability tension (see the LOW_FITNESS gate)
-------------------------------------------------
WQ fitness = sharpe * sqrt(|returns| / max(turnover, 0.125)). Ultra-low
turnover with small returns therefore caps fitness far below the 1.0
LOW_FITNESS limit. "Low turnover" here means *as low as possible while
still clearing the submission checks* (turnover <= 0.25), not the absolute
minimum (which is unsubmittable). The objective climbs toward Sharpe>=1.25
AND fitness>=1.0 first, then prefers the lowest turnover / drawdown.

Authority note (see CLAUDE.md): the WQ Brain `/simulations` endpoint is the
canonical backtest. There is NO local yfinance proxy here because the
curated universe includes non-PV fundamentals the local backtest cannot
evaluate.

Run:
    python -m mining_pipeline.agent_workflow --pool 24 --trials 56
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable

import optuna

from .expressions import integer_positions, parameterize

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent-workflow")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# Any field id matching this is an implied-volatility field and is BANNED
# (user constraint "避免IV字段"). The curated universe never contains one,
# and ValidatorAgent re-checks every expression as a safety net.
IV_PATTERN = re.compile(r"impl(ied)?[_ ]?vol|fair.?vol|fair.?impl|\biv\b|vega|implvol", re.I)


# ---------------------------------------------------------------------------
# Agent 1: FieldAgent - curated non-IV field universe (verified on account)
# ---------------------------------------------------------------------------

class FieldAgent:
    """Owns the NON-IV field universe used by all downstream agents.

    PV fields are the standard WorldQuant price/volume primitives. The
    fundamental ids are all confirmed present on this account at
    (USA, TOP3000, delay=1) via /data-fields. The entire `option` category
    (where implied-vol lives) is excluded outright.
    """

    PV = ("close", "open", "high", "low", "volume", "vwap", "returns",
          "cap", "sharesout", "adv20")

    VALUE_NUM = ("income", "sales", "revenue", "equity", "operating_income",
                 "retained_earnings", "pretax_income", "working_capital",
                 "invested_capital", "income_beforeextra")
    QUALITY = ("return_assets", "return_equity")
    MARGIN_NUM = ("income", "operating_income", "pretax_income")
    MARGIN_DEN = ("sales", "revenue")
    LEVER_NUM = ("debt", "debt_lt", "liabilities", "liabilities_curr")
    LEVER_DEN = ("equity", "assets")
    SCALE_DEN = ("cap", "assets", "equity")

    ALL_FUNDAMENTAL = tuple(sorted(set(
        VALUE_NUM + QUALITY + MARGIN_NUM + MARGIN_DEN +
        LEVER_NUM + LEVER_DEN + SCALE_DEN + ("assets",)
    )))

    def __init__(self):
        bad = [f for f in self.PV + self.ALL_FUNDAMENTAL if IV_PATTERN.search(f)]
        if bad:
            raise ValueError(f"IV field leaked into curated universe: {bad}")

    def verify(self, session) -> dict:
        """Confirm each curated fundamental id exists on the account at d=1.
        Drops any that are missing. Returns {field: bool}.
        """
        base = "https://api.worldquantbrain.com/data-fields"
        common = dict(region="USA", universe="TOP3000", delay=1,
                      instrumentType="EQUITY")
        status = {}
        for fid in self.ALL_FUNDAMENTAL:
            ok = False
            for attempt in range(4):
                r = session.get(base, params={**common, "search": fid, "limit": 25},
                                timeout=30)
                if r.status_code == 429:
                    time.sleep(6 * (attempt + 1)); continue
                if r.status_code == 200:
                    ids = {d.get("id") for d in (r.json().get("results") or [])}
                    ok = fid in ids
                break
            status[fid] = ok
            time.sleep(0.4)
        missing = [f for f, ok in status.items() if not ok]
        if missing:
            log.warning(f"FieldAgent: dropping {len(missing)} unverified: {missing}")
            self._drop(missing)
        return status

    def _drop(self, missing: list[str]):
        m = set(missing)
        for attr in ("VALUE_NUM", "QUALITY", "MARGIN_NUM", "MARGIN_DEN",
                     "LEVER_NUM", "LEVER_DEN", "SCALE_DEN"):
            setattr(self, attr, tuple(x for x in getattr(self, attr) if x not in m))


# ---------------------------------------------------------------------------
# Agent 2: HypothesisAgent - original archetypes (+ per-class window range)
# ---------------------------------------------------------------------------

@dataclass
class Archetype:
    name: str
    build: Callable[[random.Random, "FieldAgent"], str]
    win_lo: int = 20          # window search range for this archetype's ts ops
    win_hi: int = 120
    klass: str = "fund"       # fund | mix | pv  (for logging/diversity only)


class HypothesisAgent:
    """Produces original factor archetypes - generic financial anomalies
    *constructed here*, NOT copied from Alpha101 or the project's classical
    factor library (reuse of those is forbidden by spec).

    Slow balance-sheet signals -> very low turnover but low Sharpe/fitness.
    Short reversal / volume / intraday signals -> higher Sharpe & returns
    (so they can clear the fitness gate) at moderate turnover. The sign of
    each alpha is left to the SimulatorAgent to choose.
    """

    @staticmethod
    def _ratio(rng, num_pool, den_pool):
        return f"divide({rng.choice(num_pool)}, {rng.choice(den_pool)})"

    def archetypes(self) -> list[Archetype]:
        A = Archetype
        # v2 - focused on the v1 winners (leverage anchor SH=1.02 TO=0.010 DD=0.078,
        # vol_scaled_reversal SH=1.35) and orthogonal combos that should lift
        # Sharpe past 1.25 while keeping TO under 0.25.
        return [
            # ---- proven anchors: leverage variants (low TO + low DD) ----
            A("leverage", lambda r, f:
              f"rank({self._ratio(r, f.LEVER_NUM, f.LEVER_DEN)})", klass="fund"),
            A("leverage_lia_assets", lambda r, f:
              f"rank(divide(liabilities, assets))", klass="fund"),
            A("leverage_debt_eq", lambda r, f:
              f"rank(divide(debt, equity))", klass="fund"),
            A("leverage_debt_lt_assets", lambda r, f:
              f"rank(divide(debt_lt, assets))", klass="fund"),
            A("leverage_liacurr_assets", lambda r, f:
              f"rank(divide(liabilities_curr, assets))", klass="fund"),
            # ---- earnings-yield momentum (SH 0.89 in v1) ----
            A("earnings_yield_mom", lambda r, f:
              f"rank(ts_delta(divide(income, cap), 60))",
              win_lo=20, win_hi=180, klass="fund"),
            A("earnings_yield_mom_long", lambda r, f:
              f"rank(ts_delta(divide({r.choice(('income','operating_income','pretax_income'))}, cap), 120))",
              win_lo=60, win_hi=250, klass="fund"),
            # ---- vol-scaled reversal at LONGER windows (v1 used 2-15 -> TO 0.40
            #      blew the user's 0.25 cap; pushed to 15-40 to halve turnover) ----
            A("vol_scaled_reversal_slow", lambda r, f:
              f"rank(divide(ts_delta(close, 20), ts_std_dev(returns, 20)))",
              win_lo=15, win_hi=40, klass="pv"),
            # ---- ORTHOGONAL COMBOS: stack the leverage anchor with an
            #      uncorrelated signal so Sharpe diversifies up while
            #      TO stays low (PV reversal moves slowly when window is long,
            #      low_vol barely moves at all) ----
            A("leverage_plus_revers", lambda r, f:
              f"add(zscore(rank(divide(liabilities, assets))), "
              f"zscore(rank(divide(ts_delta(close, 20), ts_std_dev(returns, 20)))))",
              win_lo=15, win_hi=40, klass="mix"),
            A("leverage_plus_lowvol", lambda r, f:
              f"add(zscore(rank(divide(liabilities, assets))), "
              f"zscore(reverse(rank(ts_std_dev(returns, 60)))))",
              win_lo=20, win_hi=120, klass="mix"),
            A("leverage_plus_earnyld", lambda r, f:
              f"add(zscore(rank(divide(liabilities, assets))), "
              f"zscore(rank(ts_delta(divide(income, cap), 60))))",
              win_lo=20, win_hi=180, klass="mix"),
            A("leverage_plus_quality", lambda r, f:
              f"add(zscore(rank(divide(liabilities, assets))), "
              f"zscore(rank({r.choice(f.QUALITY)})))", klass="mix"),
            # ---- triple-stack: three orthogonal sources (leverage + earnings
            #      yield momentum + slow reversal) for max Sharpe diversification ----
            A("triple_stack", lambda r, f:
              f"add(add(zscore(rank(divide(liabilities, assets))), "
              f"zscore(rank(ts_delta(divide(income, cap), 60)))), "
              f"zscore(rank(divide(ts_delta(close, 20), ts_std_dev(returns, 20)))))",
              win_lo=20, win_hi=180, klass="mix"),
            A("triple_fund_stack", lambda r, f:
              f"add(add(zscore(rank(divide(liabilities, assets))), "
              f"zscore(rank({r.choice(f.QUALITY)}))), "
              f"zscore(rank(ts_delta(divide(income, cap), 60))))",
              win_lo=20, win_hi=180, klass="mix"),
            # ---- defensive low-vol + reversal mix (no fundamentals) ----
            A("revers_plus_lowvol", lambda r, f:
              f"add(zscore(rank(divide(ts_delta(close, 20), ts_std_dev(returns, 20)))), "
              f"zscore(reverse(rank(ts_std_dev(returns, 60)))))",
              win_lo=15, win_hi=80, klass="pv"),
            # ---- one solo quality / value baseline kept for diversity ----
            A("quality_ratio", lambda r, f:
              f"rank({r.choice(f.QUALITY)})", klass="fund"),
        ]


# ---------------------------------------------------------------------------
# Agent 3: GeneratorAgent - instantiate archetypes into a diverse pool
# ---------------------------------------------------------------------------

@dataclass
class PoolItem:
    name: str
    expr: str
    win_lo: int
    win_hi: int
    klass: str


class GeneratorAgent:
    def __init__(self, fields: FieldAgent, hypotheses: HypothesisAgent):
        self.fields = fields
        self.archs = hypotheses.archetypes()

    def generate(self, n: int, seed: int) -> list[PoolItem]:
        rng = random.Random(seed)
        out, seen = [], set()
        order = list(self.archs)
        tries = 0
        while len(out) < n and tries < n * 14:
            arch = order[len(out) % len(order)] if tries < len(order) else rng.choice(order)
            expr = arch.build(rng, self.fields)
            tries += 1
            if IV_PATTERN.search(expr) or expr in seen:
                continue
            seen.add(expr)
            out.append(PoolItem(arch.name, expr, arch.win_lo, arch.win_hi, arch.klass))
        return out


# ---------------------------------------------------------------------------
# Agent 4: SimulatorAgent - WQ Brain submit + ONE joint Optuna study
# ---------------------------------------------------------------------------

# Settings biased toward low turnover (decay) and low drawdown
# (neutralization on, moderate truncation). delay fixed to 1 (D1, per user).
SETTING_SPACE = {
    # v1 evidence: TOP3000 was where the best Sharpe and lowest TO/DD landed;
    # TOP500/TOP1000 frequently tripped LOW_SUB_UNIVERSE_SHARPE. Higher decay
    # (16-64) smooths turnover for the leverage anchor. Lower truncation drives
    # weight concentration up but lifts Sharpe; 0.02-0.05 won.
    "universe":       ["TOP3000", "TOP1000"],
    "delay":          [1],
    "decay":          [16, 32, 64, 128],
    "truncation":     [0.02, 0.05, 0.08],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR"],
    "pasteurization": ["ON"],
}
FIXED_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "language": "FASTEXPR",
    "unitHandling": "VERIFY", "nanHandling": "OFF", "visualization": False,
    "maxTrade": "OFF", "testPeriod": "P0Y0M",
}

SHARPE_FLOOR = 1.25       # WQ LOW_SHARPE check limit
FITNESS_FLOOR = 1.0       # WQ LOW_FITNESS check limit
TURNOVER_CEIL = 0.25      # user: low turnover (stricter than WQ's 0.70)


@dataclass
class TrialResult:
    ok: bool
    archetype: str
    expression: str
    optimized: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    margin: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    checks: list = field(default_factory=list)
    checks_passed: int = 0
    checks_total: int = 0
    pending: int = 0
    submittable: bool = False
    alpha_id: str = ""
    error: str = ""


def _submittable(checks: list) -> tuple[bool, int, int, int]:
    """Submittable iff every NON-PENDING IS check is PASS.
    Returns (submittable, n_pass, n_total, n_pending).
    """
    n_pass = sum(1 for c in checks if c.get("result") == "PASS")
    n_pending = sum(1 for c in checks if c.get("result") == "PENDING")
    n_fail = sum(1 for c in checks if c.get("result") not in ("PASS", "PENDING"))
    return (n_fail == 0 and n_pass > 0), n_pass, len(checks), n_pending


class SimulatorAgent:
    POLL_TIMEOUT_S = 600
    POLL_INTERVAL_S = 5

    def __init__(self, session):
        self.session = session

    def submit(self, expression: str, settings: dict) -> TrialResult:
        full = dict(FIXED_SETTINGS); full.update(settings)
        body = {"type": "REGULAR", "settings": full, "regular": expression}
        r = None
        for attempt in range(10):
            r = self.session.post("https://api.worldquantbrain.com/simulations",
                                  json=body, timeout=30)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After") or 20)
                log.info(f"      429 ({r.text[:55].strip()}); sleep {wait:.0f}s")
                time.sleep(wait); continue
            break
        if r is None or r.status_code != 201:
            return TrialResult(False, "", expression, expression, full,
                               error=f"submit-{getattr(r,'status_code','?')}: {getattr(r,'text','')[:200]}")
        loc = r.headers.get("Location")
        if not loc:
            return TrialResult(False, "", expression, expression, full,
                               error="no Location header")
        t0 = time.time()
        while time.time() - t0 < self.POLL_TIMEOUT_S:
            time.sleep(self.POLL_INTERVAL_S)
            rp = self.session.get(loc, timeout=30)
            if rp.status_code == 429:
                time.sleep(20); continue
            if rp.status_code != 200:
                continue
            data = rp.json(); st = data.get("status", "")
            if st == "COMPLETE":
                aid = data.get("alpha")
                ra = self.session.get(
                    f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
                if ra.status_code != 200:
                    return TrialResult(False, "", expression, expression, full,
                                       alpha_id=aid or "",
                                       error=f"alpha-get-{ra.status_code}")
                isb = (ra.json().get("is") or {})
                checks = [{"name": c.get("name"), "result": c.get("result"),
                           "value": c.get("value"), "limit": c.get("limit")}
                          for c in (isb.get("checks") or [])]
                sub, npass, ntot, npend = _submittable(checks)
                return TrialResult(
                    True, "", expression, expression, full,
                    sharpe=float(isb.get("sharpe") or 0.0),
                    turnover=float(isb.get("turnover") or 0.0),
                    fitness=float(isb.get("fitness") or 0.0),
                    returns=float(isb.get("returns") or 0.0),
                    drawdown=float(isb.get("drawdown") or 0.0),
                    margin=float(isb.get("margin") or 0.0),
                    longCount=int(isb.get("longCount") or 0),
                    shortCount=int(isb.get("shortCount") or 0),
                    checks=checks, checks_passed=npass, checks_total=ntot,
                    pending=npend, submittable=sub, alpha_id=aid or "")
            if st in ("ERROR", "FAILED", "WARNING"):
                return TrialResult(False, "", expression, expression, full,
                                   error=f"sim-{st}: {str(data.get('message',''))[:200]}")
        return TrialResult(False, "", expression, expression, full,
                           error="poll-timeout")

    @staticmethod
    def _score(res: TrialResult) -> float:
        """Climb toward BOTH submission gates, then prefer low TO / low DD.

        - progress term rewards approaching Sharpe>=1.25 AND fitness>=1.0
          (each capped at its gate so it doesn't chase extreme values);
        - a big bonus once every non-pending check passes (submittable);
        - a HARD penalty for turnover above the user's 0.25 cap, plus a mild
          preference for lower turnover and lower drawdown among the rest.
        """
        if not res.ok:
            return -5.0
        progress = min(res.sharpe, SHARPE_FLOOR) / SHARPE_FLOOR \
            + min(res.fitness, FITNESS_FLOOR) / FITNESS_FLOOR
        sub_bonus = 2.0 if res.submittable else 0.0
        to_hard = 2.0 * max(0.0, res.turnover - TURNOVER_CEIL)
        to_soft = 0.5 * res.turnover
        dd_pen = 1.0 * res.drawdown
        return progress + sub_bonus - to_hard - to_soft - dd_pen

    def study(self, pool: list[PoolItem], n_trials: int, seed: int,
              sink: Callable[[TrialResult], None],
              logged: list[TrialResult]) -> list[TrialResult]:
        """ONE TPE study over (expression, sign, windows, settings).

        Appends every TrialResult to `logged` (shared with the caller so the
        sink can persist partial progress) and returns it.
        """
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        st = optuna.create_study(direction="maximize",
                                 sampler=optuna.samplers.TPESampler(seed=seed))
        idx = list(range(len(pool)))

        def objective(trial: optuna.trial.Trial) -> float:
            i = trial.suggest_categorical("expr_id", idx)
            item = pool[i]
            settings = {k: trial.suggest_categorical(k, v)
                        for k, v in SETTING_SPACE.items()}
            positions = integer_positions(item.expr)
            windows = {p: trial.suggest_int(f"w{i}_{p}", item.win_lo, item.win_hi)
                       for p in positions}
            sign = trial.suggest_categorical("sign", [1, -1])
            expr = parameterize(item.expr, windows) if windows else item.expr
            if sign == -1:
                expr = f"reverse({expr})"
            log.info(f"   t{trial.number}: [{item.name}] sign={sign:+d} win={windows} "
                     f"u={settings['universe']} dec={settings['decay']} "
                     f"neut={settings['neutralization']} tr={settings['truncation']}")
            res = self.submit(expr, settings)
            res.archetype = item.name
            logged.append(res); sink(res)
            if not res.ok:
                log.info(f"      [{res.error[:90]}]")
                return -5.0
            mark = "SUBMITTABLE" if res.submittable else f"{res.checks_passed}/{res.checks_total}p{res.pending}"
            log.info(f"      SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                     f"FIT={res.fitness:+.3f} DD={res.drawdown:.3f} ret={res.returns:+.3f} "
                     f"[{mark}] {res.alpha_id}")
            return self._score(res)

        st.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        return logged


# ---------------------------------------------------------------------------
# Agent 5: ValidatorAgent - submittability gate + low-TO/low-DD ranking
# ---------------------------------------------------------------------------

class ValidatorAgent:
    @staticmethod
    def desirability(r: TrialResult) -> float:
        # Among submittable alphas: lower turnover & drawdown better,
        # higher fitness/sharpe better.
        return r.fitness + 0.3 * r.sharpe - 2.0 * r.drawdown - 2.0 * r.turnover

    def select(self, results: list[TrialResult]) -> dict:
        for r in results:
            if r.ok and IV_PATTERN.search(r.optimized):
                r.submittable = False
                r.error = "IV field detected post-hoc"  # should never happen
        submittable = [r for r in results if r.ok and r.submittable
                       and r.sharpe >= SHARPE_FLOOR
                       and r.fitness >= FITNESS_FLOOR
                       and 0.0 < r.turnover < TURNOVER_CEIL]
        submittable.sort(key=self.desirability, reverse=True)
        near = [r for r in results if r.ok and not (r in submittable)
                and r.sharpe >= 0.8]
        near.sort(key=lambda r: (r.submittable, r.sharpe), reverse=True)
        return {"submittable": submittable, "near_miss": near}


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
    ap.add_argument("--pool", type=int, default=24,
                    help="number of concrete expressions in the search pool")
    ap.add_argument("--trials", type=int, default=56,
                    help="total WQ simulations (TPE trials) across the pool")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--verify-fields", action="store_true",
                    help="verify curated fields against the account first")
    ap.add_argument("--out", type=str, default="WQ_AGENT_REPORT.json")
    ap.add_argument("--survivors-out", type=str,
                    default="WQ_SUBMITTABLE_CANDIDATES.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"[Agent0] authenticated as {cm.credentials.username}")

    fields = FieldAgent()
    if args.verify_fields:
        log.info("[FieldAgent] verifying curated non-IV fields on account ...")
        fields.verify(cm.session)
    gen = GeneratorAgent(fields, HypothesisAgent())
    pool = gen.generate(args.pool, seed=args.seed)
    log.info(f"[GeneratorAgent] pool of {len(pool)} expressions:")
    for it in pool:
        log.info(f"   [{it.klass}] {it.name:<20} {it.expr}")

    log.info(f"[SimulatorAgent] one TPE study, {args.trials} WQ simulations "
             f"(~{args.trials*110/60:.0f} min at ~110s/sim, delay=1)")

    sim = SimulatorAgent(cm.session)
    all_results: list[TrialResult] = []

    def sink(_r):  # persist after every single simulation
        with open(args.out, "w") as f:
            json.dump([asdict(x) for x in all_results], f, indent=2)

    sim.study(pool, args.trials, args.seed, sink, all_results)
    sink(None)

    sel = ValidatorAgent().select(all_results)
    survivors = sel["submittable"]
    with open(args.survivors_out, "w") as f:
        json.dump([asdict(x) for x in survivors], f, indent=2)

    print("\n" + "=" * 122)
    ok_n = sum(1 for r in all_results if r.ok)
    print(f"simulations: {ok_n}/{len(all_results)} completed | "
          f"SUBMITTABLE survivors (all checks PASS, SH>={SHARPE_FLOOR}, "
          f"FIT>={FITNESS_FLOOR}, TO<{TURNOVER_CEIL}): {len(survivors)}")
    print(f"\n{'SH':>6}{'TO':>7}{'FIT':>7}{'DD':>7}{'ret':>7}  {'alpha_id':<10} "
          f"{'universe':<9}{'neut':<12} archetype / expression")
    for r in survivors[:25]:
        s = r.settings
        print(f"{r.sharpe:6.2f}{r.turnover:7.3f}{r.fitness:7.2f}{r.drawdown:7.3f}"
              f"{r.returns:7.3f}  {r.alpha_id:<10} {s.get('universe'):<9}"
              f"{s.get('neutralization'):<12} {r.archetype}: {r.optimized[:58]}")
    if not survivors:
        print("\n(no fully-submittable survivors; top results by Sharpe:)")
        for r in sel["near_miss"][:15]:
            fails = [c['name'] for c in r.checks
                     if c.get('result') not in ('PASS', 'PENDING')]
            print(f"{r.sharpe:6.2f}{r.turnover:7.3f}{r.fitness:7.2f}{r.drawdown:7.3f}"
                  f"{r.returns:7.3f}  {r.alpha_id:<10} fails={fails} "
                  f"{r.archetype}: {r.optimized[:48]}")
    print("=" * 122)
    log.info(f"wrote {args.out} (all trials) and {args.survivors_out} (survivors)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
