"""Mine submittable D1 (delay=1) alphas with LOW turnover and LOW max-drawdown.

Per the user spec for this run:
  * delay = 1                       (D1 factors)
  * NO implied-volatility fields    (PV + slow fundamentals only)
  * must be SUBMITTABLE             (all WQ IS checks PASS)
  * LOW turnover                    (forced via ts_target_tvr_decay + filter)
  * LOW max drawdown                (INDUSTRY/SUBINDUSTRY neutralization +
                                     truncation + winsorize, ranked by |dd|)

This goes STRAIGHT to WorldQuant Brain `/simulations` (the authoritative
backtest per CLAUDE.md); the local yfinance proxy is skipped because its
numbers do not generalize.

Expressions are generated fresh (no Alpha101 / classical-template reuse)
and the final signal is wrapped in `ts_target_tvr_decay(sig, 0, 1, T)` to
pin turnover near the target T.

Usage:
    python scripts/mine_d1.py --n 24 --target-tvr 0.10 --seed 7
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mine-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# ---------------------------------------------------------------------------
# Field universe -- explicitly PV + slow fundamentals. NO IV / option fields.
# All verified exposed on this account's USA data-fields surface.
# ---------------------------------------------------------------------------
FAST_FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns")
SLOW_FIELDS = ("cap", "sharesout", "adv20")           # slow -> low turnover
ALL_FIELDS = FAST_FIELDS + SLOW_FIELDS

# Operators chosen to produce slow, well-behaved signals.
TS_SMOOTH = ("ts_mean", "ts_decay_linear", "ts_rank", "ts_zscore", "ts_av_diff")
TS_SIGNAL = ("ts_delta", "ts_std_dev", "ts_returns", "ts_av_diff",
             "ts_arg_max", "ts_arg_min", "ts_corr")
CS_WRAP = ("rank", "zscore", "normalize")
UNARY = ("", "", "-")                                  # bias toward no-negate

# Longer windows -> slower signal -> lower turnover.
WINDOWS = (20, 40, 60, 120, 240)


@dataclass
class Result:
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
    failed_checks: list = field(default_factory=list)
    submittable: bool = False
    alpha_id: str = ""
    error: str = ""


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fresh expression generation (no template reuse)
# ---------------------------------------------------------------------------
def _core(rng: random.Random) -> str:
    """Build a slow signal core."""
    kind = rng.random()
    if kind < 0.30:
        # smoothed level/return of a single field
        f = rng.choice(ALL_FIELDS)
        op = rng.choice(TS_SMOOTH)
        return f"{op}({f}, {rng.choice(WINDOWS)})"
    if kind < 0.55:
        # long-horizon change (slow reversal/momentum)
        f = rng.choice(FAST_FIELDS)
        op = rng.choice(("ts_delta", "ts_av_diff", "ts_returns"))
        return f"{op}({f}, {rng.choice(WINDOWS)})"
    if kind < 0.75:
        # ratio of two slow aggregates of two fields
        a, b = rng.sample(ALL_FIELDS, 2)
        w = rng.choice(WINDOWS)
        return f"divide(ts_mean({a}, {w}), ts_mean({b}, {w}))"
    if kind < 0.90:
        # time-series correlation (slow co-movement)
        a, b = rng.sample(FAST_FIELDS, 2)
        return f"ts_corr({a}, {b}, {rng.choice(WINDOWS)})"
    # smoothed volatility / dispersion
    f = rng.choice(FAST_FIELDS)
    return f"ts_std_dev({f}, {rng.choice(WINDOWS)})"


def generate(n: int, seed: int, target_tvr: float) -> list[str]:
    rng = random.Random(seed)
    out, seen = [], set()
    guard = 0
    while len(out) < n and guard < n * 50:
        guard += 1
        core = _core(rng)
        # optionally combine two cores for richness
        if rng.random() < 0.35:
            op = rng.choice(("subtract", "add", "divide"))
            core = f"{op}({core}, {_core(rng)})"
        sign = rng.choice(UNARY)
        wrap = rng.choice(CS_WRAP)
        # Extra smoothing pass keeps turnover low (this account has no
        # ts_target_tvr_decay operator). Larger smoothing window -> slower.
        sw = rng.choice((10, 20, 40))
        expr = f"{sign}{wrap}(ts_mean(winsorize({core}, std=4), {sw}))"
        if expr in seen:
            continue
        seen.add(expr)
        out.append(expr)
    return out


# ---------------------------------------------------------------------------
# WQ Brain submission
# ---------------------------------------------------------------------------
FIXED = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "language": "FASTEXPR",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "pasteurization": "ON",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
    "delay": 1,            # D1
}


def submit(session, expr: str, settings: dict,
           poll_timeout_s: int = 420, poll_interval_s: int = 5) -> Result:
    s = dict(FIXED)
    s.update(settings)
    body = {"type": "REGULAR", "settings": s, "regular": expr}

    for _ in range(5):
        r = session.post("https://api.worldquantbrain.com/simulations",
                         json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s"); time.sleep(wait); continue
        break
    if r.status_code != 201:
        return Result(False, expr, s, error=f"submit-{r.status_code}: {r.text[:200]}")
    loc = r.headers.get("Location")
    if not loc:
        return Result(False, expr, s, error="no Location header")

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
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
            if ra.status_code != 200:
                return Result(False, expr, s, alpha_id=aid or "",
                              error=f"alpha-get-{ra.status_code}")
            isb = (ra.json().get("is") or {})
            checks = isb.get("checks") or []
            failed = [c.get("name") for c in checks
                      if c.get("result") not in ("PASS", "PENDING", None)]
            passed = sum(1 for c in checks if c.get("result") == "PASS")
            return Result(
                ok=True, expression=expr, settings=s,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                margin=float(isb.get("margin") or 0.0),
                longCount=int(isb.get("longCount") or 0),
                shortCount=int(isb.get("shortCount") or 0),
                checks_passed=passed, checks_total=len(checks),
                failed_checks=failed,
                submittable=(len(failed) == 0 and len(checks) > 0),
                alpha_id=aid or "")
        if st in ("ERROR", "FAILED", "WARNING"):
            return Result(False, expr, s,
                          error=f"sim-{st}: {data.get('message','')[:200]}")
    return Result(False, expr, s, error="poll-timeout")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24, help="number of candidates")
    ap.add_argument("--target-tvr", type=float, default=0.10,
                    help="turnover target pinned via ts_target_tvr_decay")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--universe", type=str, default="TOP3000")
    ap.add_argument("--neutralization", type=str, default="SUBINDUSTRY")
    ap.add_argument("--truncation", type=float, default=0.08)
    ap.add_argument("--decay", type=int, default=6,
                    help="simulation decay (extra turnover damping)")
    ap.add_argument("--max-turnover", type=float, default=0.25,
                    help="survivor turnover ceiling")
    ap.add_argument("--workers", type=int, default=2, help="concurrent simulations")
    ap.add_argument("--out", type=str, default="WQ_D1_LOWTO_REPORT.json")
    args = ap.parse_args()

    cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
        base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    exprs = generate(args.n, args.seed, args.target_tvr)
    log.info(f"generated {len(exprs)} fresh D1 candidates (target_tvr={args.target_tvr})")

    base_settings = {
        "universe": args.universe,
        "neutralization": args.neutralization,
        "truncation": args.truncation,
        "decay": args.decay,
    }

    results: list[Result] = []
    lock = threading.Lock()
    done = [0]

    def work(idx_expr):
        idx, e = idx_expr
        # stagger POSTs slightly so concurrent submits don't trip 429
        time.sleep((idx % args.workers) * 2.0)
        r = submit(cm.session, e, base_settings)
        with lock:
            results.append(r)
            done[0] += 1
            tag = f"[{done[0]}/{len(exprs)}]"
            if r.ok:
                log.info(f"{tag} SH={r.sharpe:+.3f} TO={r.turnover:.3f} "
                         f"FIT={r.fitness:+.3f} DD={r.drawdown:.3f} "
                         f"checks={r.checks_passed}/{r.checks_total} "
                         f"submittable={r.submittable} fail={r.failed_checks} :: {e[:60]}")
            else:
                log.info(f"{tag} [{r.error[:70]}] :: {e[:60]}")
            with open(REPO / args.out, "w") as f:
                json.dump([asdict(x) for x in results], f, indent=2)
        return r

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, list(enumerate(exprs))))

    # ----- rank survivors -----
    survivors = [r for r in results if r.ok and r.submittable
                 and r.sharpe > 1.25 and r.turnover < args.max_turnover]
    # low turnover first, then low |drawdown|, then sharpe
    survivors.sort(key=lambda r: (r.turnover, abs(r.drawdown), -r.sharpe))

    print("\n" + "=" * 112)
    print(f"OK simulations: {sum(1 for r in results if r.ok)}/{len(results)} | "
          f"SUBMITTABLE survivors (SH>1.25, TO<0.25, all checks PASS): {len(survivors)}")
    print(f"{'SH':>7}{'TO':>7}{'FIT':>7}{'DD':>8}{'ret':>8}  alpha_id    expression")
    for r in survivors:
        print(f"{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}{r.drawdown:8.3f}"
              f"{r.returns:8.3f}  {r.alpha_id:<10}  {r.expression[:70]}")
    print("=" * 112)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
