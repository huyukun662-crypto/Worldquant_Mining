"""D1 low-turnover / low-maxdd mining orchestrator (5-stage workflow).

Goal (per user spec): mine **delay=1 (D1)** alphas that are
**submittable** on WorldQuant Brain, with **low turnover** and **low max
drawdown**, while **avoiding IV (implied-volatility) fields**.

This is organised as five explicit stages ("agents"):

  1. FIELD AGENT      -- choose the input field universe. Only PV + a few
                         robust, always-present fundamentals. NO IV / option
                         implied-vol fields (anything matching `*implied*`,
                         `*_iv*`, `mdl*_iv`, etc. is excluded by construction).
  2. GENERATOR AGENT  -- build FRESH expressions (no Alpha101 / classical
                         template reuse, per CLAUDE.md). Generation is biased
                         toward low-turnover constructs: smoothing via
                         ts_mean / ts_decay_linear over long windows, wrapped
                         in a cross-sectional rank/zscore.
  3. TRIAGE AGENT     -- cheap local sanity check: the expression must parse
                         and the local backtest must not blow up. This only
                         throws out garbage; the numbers are NOT trusted.
  4. SIMULATION AGENT -- submit (expression, settings) to WQ Brain
                         `/simulations`, delay fixed at 1, Optuna over the
                         joint (windows, decay, neutralization, universe,
                         truncation) space.
  5. SELECTION AGENT  -- rank by a composite that rewards Sharpe and
                         penalises turnover + drawdown + failed checks; keep
                         the submittable survivors.

Authoritative thresholds (applied to WQ-platform numbers):
    WQ_IS_Sharpe   > 1.25
    WQ_IS_Turnover < 0.25
    drawdown       : minimise (reported separately, soft objective)

Run:
    python -m mining_pipeline.wq_d1_pipeline --trials 3 --out WQ_MINING_REPORT.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import optuna

from .expressions import integer_positions, parameterize

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wq-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# ---------------------------------------------------------------------------
# STAGE 1 -- FIELD AGENT
# ---------------------------------------------------------------------------
# PV + robust fundamentals exposed at delay=1 on this account. Explicitly NO
# IV / implied-volatility / option-greeks fields. A field is rejected if its
# name contains any of the IV markers below.
IV_MARKERS = ("implied", "_iv", "iv_", "ivol", "vega", "gamma", "theta",
              "delta_iv", "vol_surface", "skew")

FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns",
          "cap", "sharesout", "adv20")


def _assert_no_iv(fields):
    bad = [f for f in fields if any(m in f.lower() for m in IV_MARKERS)]
    if bad:
        raise ValueError(f"IV fields are forbidden but found: {bad}")
    return tuple(fields)


FIELDS = _assert_no_iv(FIELDS)

# ---------------------------------------------------------------------------
# STAGE 4 -- setting search space. Delay is FIXED at 1 (D1 mandate).
# decay/neutralization reduce both turnover and drawdown, so the space is
# tilted toward higher decay and risk-neutralized books.
# ---------------------------------------------------------------------------
SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000", "TOP500"],
    "delay":          [1],
    "decay":          [8, 16, 32, 64],          # higher decay -> lower turnover
    "truncation":     [0.02, 0.05, 0.08],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"],
    "pasteurization": ["ON"],
}

# Focused batch: batch-1 showed turnover sat at 0.03-0.10 vs the 0.25 cap, so
# there is ample turnover headroom to spend on Sharpe. Lower decay / lighter
# smoothing lifts Sharpe while staying well under the cap.
SETTING_SPACE_FOCUSED = {
    "universe":       ["TOP3000", "TOP1000"],
    "delay":          [1],
    "decay":          [0, 2, 4, 8],             # spend turnover headroom on Sharpe
    "truncation":     [0.02, 0.05, 0.08],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY"],   # keep drawdown contained
    "pasteurization": ["ON"],
}

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
}

SHARPE_FLOOR = 1.25
TURNOVER_CEILING = 0.25


# Fine-tune batch-3: tight neighbourhood around the batch-2 near-misses. The
# champion `rank(reverse(ts_av_diff(close, 20)))` hit SH 1.21 / TO 0.221 / DD
# 0.079 at decay=4; turnover still has headroom, so we sweep low decays and
# nearby windows to nudge Sharpe past 1.25 while keeping turnover < 0.25.
SETTING_SPACE_FINETUNE = {
    "universe":       ["TOP3000", "TOP1000"],
    "delay":          [1],
    "decay":          [2, 3, 4, 5, 6],
    "truncation":     [0.05, 0.08],
    "neutralization": ["SUBINDUSTRY", "INDUSTRY"],
    "pasteurization": ["ON"],
}

# All four have only lookback-window literals (no semantic constants), so
# window tuning is safe here.
FINETUNE_FAMILIES = [
    "rank(reverse(ts_av_diff(close, 20)))",
    "zscore(reverse(ts_av_diff(close, 20)))",
    "rank(reverse(ts_av_diff(vwap, 20)))",
    "zscore(add(reverse(ts_av_diff(vwap, 20)), reverse(ts_delta(close, 5))))",
]


# ---------------------------------------------------------------------------
# STAGE 2 -- GENERATOR AGENT
# ---------------------------------------------------------------------------
# Fresh, intuition-guided low-turnover families. These are NOT copied from
# Alpha101 / the classical library; they are generic operator x field motifs
# that the search stage will parameterise. Every family is wrapped in a
# cross-sectional rank/zscore and smoothed to keep turnover low. The literal
# integers are placeholders the Optuna stage refines.

SMOOTH = ("ts_mean", "ts_decay_linear")
WRAP = ("rank", "zscore", "normalize")


def _seed_families(rng: random.Random, n: int) -> list[str]:
    """Build `n` distinct low-turnover seed expressions from generic motifs."""
    px = ("close", "vwap", "open")
    vol = ("volume", "adv20")

    # NOTE: only operators verified accessible on this account tier are used
    # (see /operators -- `ts_returns` is NOT accessible; returns are built
    # from ts_delta/ts_delay or the raw `returns` field).
    def motif(rng):
        p = rng.choice(px)
        v = rng.choice(vol)
        sm = rng.choice(SMOOTH)
        wr = rng.choice(WRAP)
        kind = rng.randint(0, 7)
        if kind == 0:    # smoothed mean reversion on the raw returns field
            core = f"{sm}(reverse(returns), 20)"
        elif kind == 1:  # volatility-scaled reversal of price change
            core = f"{sm}(divide(reverse(ts_delta({p}, 5)), ts_std_dev({p}, 20)), 10)"
        elif kind == 2:  # price/vwap dislocation, smoothed
            core = f"{sm}(divide({p}, vwap), 20)"
        elif kind == 3:  # price-volume correlation (lead/lag)
            core = f"{sm}(ts_corr({p}, {v}, 20), 10)"
        elif kind == 4:  # long-window mean reversion via ts_av_diff
            core = f"{sm}(reverse(ts_av_diff({p}, 20)), 10)"
        elif kind == 5:  # liquidity tilt
            core = f"{sm}(divide({v}, cap), 20)"
        elif kind == 6:  # smoothed momentum (returns proxy via delta/delay)
            core = f"{sm}(divide(ts_delta({p}, 20), ts_delay({p}, 20)), 10)"
        else:            # de-trended price via long-window zscore
            core = f"ts_zscore({p}, 40)"
        return f"{wr}({core})"

    seen, out = set(), []
    guard = 0
    while len(out) < n and guard < n * 50:
        guard += 1
        e = motif(rng)
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _focused_families(n: int) -> list[str]:
    """Batch-2 seeds: concentrate on the families that scored best in batch-1
    (vwap/close mean-reversion via ts_av_diff and vol-scaled price reversal),
    with lighter smoothing, fresh signal COMBINATIONS, plus winsorize / liquidity
    gating to keep drawdown bounded. All operators verified accessible. Fresh
    constructions -- no Alpha101 / classical-template reuse."""
    fams = [
        # best batch-1 family, lighter smoothing
        "zscore(reverse(ts_av_diff(vwap, 20)))",
        "rank(reverse(ts_av_diff(close, 20)))",
        # vol-scaled reversal, no extra smoothing
        "zscore(divide(reverse(ts_delta(open, 5)), ts_std_dev(open, 20)))",
        # combination of two orthogonal reversals (price level + recent change)
        "zscore(add(reverse(ts_av_diff(vwap, 20)), reverse(ts_delta(close, 5))))",
        # winsorize to cut tail drawdown
        "winsorize(zscore(reverse(ts_av_diff(vwap, 20))), std=4)",
        # price reversal de-correlated from a volume-spike signal
        "rank(subtract(reverse(ts_av_diff(close, 20)), ts_zscore(volume, 20)))",
        # light smoothing of the mean-reversion signal
        "zscore(ts_mean(reverse(ts_av_diff(vwap, 10)), 5))",
        # liquidity-gated reversal (trade only when ADV is rising)
        "trade_when(greater(adv20, ts_delay(adv20, 5)), "
        "zscore(reverse(ts_av_diff(vwap, 20))), -1)",
    ]
    return fams[:n] if n < len(fams) else fams


# ---------------------------------------------------------------------------
# STAGE 3 -- TRIAGE AGENT (local, cheap; numbers NOT trusted)
# ---------------------------------------------------------------------------
_PANEL = None
_EVAL = None


def _local_parses(expression: str) -> bool:
    """Return True if the expression evaluates locally without error."""
    try:
        import numpy as np
        from . import data as data_mod
        from .evaluator import Evaluator
        global _PANEL, _EVAL
        if _PANEL is None:
            _PANEL = data_mod.load()
            _EVAL = Evaluator(_PANEL)
        sig = _EVAL.evaluate(expression)
        return sig is not None and np.isfinite(np.nanstd(sig))
    except Exception as e:  # noqa: BLE001
        log.info(f"   [triage] skip (eval error): {e}")
        return False


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class WQResult:
    ok: bool
    expression: str
    optimized: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    submittable: bool = False
    alpha_id: str = ""
    error: str = ""


# IS checks that must PASS for an alpha to be submittable (SELF_CORRELATION is
# async / PENDING during IS and is excluded from the gate).
SUBMIT_CHECKS = {"LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
                 "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE",
                 "MATCHES_COMPETITION"}


def _submittable(checks: list[dict]) -> bool:
    by_name = {c.get("name"): c.get("result") for c in checks}
    for name in SUBMIT_CHECKS:
        res = by_name.get(name)
        if res not in (None, "PASS", "PENDING"):
            return False
    # require the headline gates explicitly present and passing
    return by_name.get("LOW_SHARPE") == "PASS" and \
        by_name.get("LOW_TURNOVER") == "PASS"


def submit(session, expression: str, settings: dict,
           poll_timeout_s: int = 600, poll_interval_s: int = 5) -> WQResult:
    full = dict(FIXED_SETTINGS)
    full.update(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expression}
    # This account tier allows only ONE concurrent simulation, so a fresh
    # POST can transiently 429 (CONCURRENT_SIMULATION_LIMIT_EXCEEDED) while a
    # prior sim drains. Retry generously (up to ~10 min) so the loop self-heals.
    for _ in range(20):
        r = session.post("https://api.worldquantbrain.com/simulations",
                         json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST ({r.text[:40]}); sleep {wait:.0f}s")
            time.sleep(wait)
            continue
        break
    if r.status_code != 201:
        return WQResult(False, expression, expression, full,
                        error=f"submit-{r.status_code}: {r.text[:200]}")
    loc = r.headers.get("Location")
    if not loc:
        return WQResult(False, expression, expression, full,
                        error="no Location header")
    t0 = time.time()
    while time.time() - t0 < poll_timeout_s:
        time.sleep(poll_interval_s)
        rp = session.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st == "COMPLETE":
            aid = data.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}",
                             timeout=30)
            if ra.status_code != 200:
                return WQResult(False, expression, expression, full,
                                alpha_id=aid or "",
                                error=f"alpha-get-{ra.status_code}")
            isb = (ra.json().get("is") or {})
            checks = isb.get("checks") or []
            return WQResult(
                ok=True, expression=expression, optimized=expression,
                settings=full,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                longCount=int(isb.get("longCount") or 0),
                shortCount=int(isb.get("shortCount") or 0),
                checks_passed=sum(1 for c in checks if c.get("result") == "PASS"),
                checks_total=len(checks),
                submittable=_submittable(checks),
                alpha_id=aid or "",
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return WQResult(False, expression, expression, full,
                            error=f"sim-{st}: {data.get('message','')[:200]}")
    return WQResult(False, expression, expression, full, error="poll-timeout")


# ---------------------------------------------------------------------------
# STAGE 5 -- composite objective: maximise Sharpe, minimise turnover + maxdd.
# ---------------------------------------------------------------------------
def _score(res: WQResult) -> float:
    if not res.ok:
        return -10.0
    score = res.sharpe
    # hard turnover cap
    if res.turnover >= TURNOVER_CEILING:
        score -= 5.0
    else:
        score += (TURNOVER_CEILING - res.turnover) * 2.0   # reward lower TO
    # minimise max drawdown (reported as positive fraction)
    score -= res.drawdown * 4.0
    # reward submittability / passing checks
    score -= 0.25 * (res.checks_total - res.checks_passed)
    if res.submittable:
        score += 1.0
    return score


def search_one(session, expression: str, n_trials: int, seed: int,
               setting_space: dict = SETTING_SPACE,
               tune_windows: bool = True) -> list[WQResult]:
    # When tune_windows is False the expression's integer literals are left
    # intact -- needed for hand-crafted seeds with semantic constants
    # (winsorize std, trade_when exit) that must not be remapped to lookbacks.
    positions = integer_positions(expression) if tune_windows else []
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    trials: list[WQResult] = []

    def objective(trial):
        settings = {k: trial.suggest_categorical(k, v)
                    for k, v in setting_space.items()}
        windows = {p: trial.suggest_int(f"w{p}", 5, 60) for p in positions}
        final = parameterize(expression, windows) if windows else expression
        log.info(f"   trial settings={ {k:settings[k] for k in ('universe','decay','neutralization','truncation')} } windows={windows}")
        res = submit(session, final, settings)
        res.optimized = final
        trials.append(res)
        if not res.ok:
            log.info(f"      [{res.error[:90]}]")
        else:
            log.info(f"      WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                     f"DD={res.drawdown:.3f} FIT={res.fitness:+.3f} "
                     f"checks={res.checks_passed}/{res.checks_total} "
                     f"submittable={res.submittable}")
        return _score(res)

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return trials


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-exprs", type=int, default=8)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", type=str, default="WQ_MINING_REPORT.json")
    ap.add_argument("--no-triage", action="store_true",
                    help="skip the local parse/backtest sanity check")
    ap.add_argument("--focused", action="store_true",
                    help="batch-2: best families + combinations, lower decay")
    ap.add_argument("--finetune", action="store_true",
                    help="batch-3: tight decay/window sweep around batch-2 near-misses")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    log.info(f"STAGE1 fields (no IV): {FIELDS}")

    rng = random.Random(args.seed)
    if args.finetune:
        setting_space = SETTING_SPACE_FINETUNE
        seeds = FINETUNE_FAMILIES[:args.n_exprs]
        tune_windows = True
        log.info(f"STAGE2 [FINETUNE] {len(seeds)} near-miss seeds (window tuning on):")
    elif args.focused:
        setting_space = SETTING_SPACE_FOCUSED
        seeds = _focused_families(args.n_exprs)
        tune_windows = False
        log.info(f"STAGE2 [FOCUSED] {len(seeds)} best-family / combination seeds:")
    else:
        setting_space = SETTING_SPACE
        seeds = _seed_families(rng, args.n_exprs)
        tune_windows = True
        log.info(f"STAGE2 generated {len(seeds)} fresh low-turnover seeds:")
    for s in seeds:
        log.info(f"   {s}")

    if not args.no_triage:
        kept = []
        for s in seeds:
            if _local_parses(s):
                kept.append(s)
            else:
                log.info(f"   [triage] dropped {s}")
        seeds = kept or seeds
        log.info(f"STAGE3 triage kept {len(seeds)} seeds")

    total = len(seeds) * args.trials
    log.info(f"STAGE4 will run ~{total} WQ simulations (~{total*100/60:.0f} min)")

    all_results: list[WQResult] = []
    for i, expr in enumerate(seeds, 1):
        log.info(f"=== [{i}/{len(seeds)}] {expr}")
        all_results.extend(search_one(cm.session, expr, args.trials,
                                       args.seed + i, setting_space,
                                       tune_windows=tune_windows))
        with open(args.out, "w") as f:
            json.dump([asdict(r) for r in all_results], f, indent=2)

    survivors = [r for r in all_results if r.ok and r.sharpe > SHARPE_FLOOR
                 and r.turnover < TURNOVER_CEILING]
    survivors.sort(key=lambda r: (r.submittable, r.sharpe, -r.drawdown),
                   reverse=True)

    print("\n" + "=" * 118)
    print(f"OK sims: {sum(1 for r in all_results if r.ok)}/{len(all_results)}   "
          f"survivors (SH>{SHARPE_FLOOR} & TO<{TURNOVER_CEILING}): {len(survivors)}   "
          f"submittable: {sum(1 for r in survivors if r.submittable)}")
    print(f"{'SH':>7}{'TO':>7}{'DD':>7}{'FIT':>7}{'sub':>5}{'chk':>7}  {'alpha':<10}{'univ':<9}{'neut':<12}expr")
    for r in survivors[:30]:
        s = r.settings
        print(f"{r.sharpe:7.3f}{r.turnover:7.3f}{r.drawdown:7.3f}{r.fitness:7.3f}"
              f"{'Y' if r.submittable else 'n':>5}{r.checks_passed:>3}/{r.checks_total:<3}"
              f"  {r.alpha_id:<10}{s.get('universe'):<9}{s.get('neutralization'):<12}{r.optimized[:60]}")
    print("=" * 118)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
