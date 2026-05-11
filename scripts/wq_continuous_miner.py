"""WQ-as-evaluator continuous miner.

Per CLAUDE.md "Backtest authority", local Sharpe does not predict WQ
Brain. This miner uses WQ Brain `/simulations` as the evaluator
directly: each candidate is one platform submission. Survivors are
defined by the WQ-side gate `is.sharpe>1.25 ∧ is.turnover<0.25 ∧
os.sharpe>=is.sharpe (when populated)` (per CLAUDE.md the OS block on
this account tier may populate asynchronously; for live mining we
require IS gate + checks-all-pass).

Strategy:
  - Stream candidates from a curated unit-clean template library
    (no random expressions — those produce unit-mismatch failures
    like vwap+volume that WQ rejects).
  - Each template has placeholder windows; for each iteration we
    instantiate one candidate with a sampled (windows, settings) pair.
  - Submit via thread pool (3 workers, matching account concurrency).
  - Track distinct survivors by structural signature.
  - Stop at N distinct survivors.
  - Save state every result (so a crash mid-run preserves work).
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import logging
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wqcm")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
SDIR = REPO / "logs" / "20260511_wq_continuous_mining"
SDIR.mkdir(parents=True, exist_ok=True)

IS_SH_FLOOR = 1.25
IS_TO_CEIL = 0.25

# Unit-clean mechanism templates. Every output is unitless / scalar-rank
# so cross-sectional ops can wrap them safely. Each `_` is a tunable
# integer-literal slot.
TEMPLATES = [
    # Volume dispersion (all unit-clean: std/mean of same field cancels)
    "rank(ts_decay_linear(divide(ts_std_dev(volume,_),ts_mean(volume,_)),_))",
    "rank(reverse(divide(ts_std_dev(volume,_),ts_mean(volume,_))))",
    "rank(divide(ts_std_dev(volume,_),ts_mean(volume,_)))",
    "rank(divide(ts_std_dev(close,_),ts_mean(close,_)))",
    # Volume CV × return reversal (unitless × unitless)
    "rank(ts_decay_linear(multiply(divide(ts_std_dev(volume,_),ts_mean(volume,_)),reverse(ts_returns(close,_))),_))",
    "rank(reverse(multiply(divide(ts_std_dev(volume,_),ts_mean(volume,_)),ts_returns(close,_))))",
    # Joint z-scores (both unitless)
    "rank(reverse(multiply(ts_zscore(volume,_),ts_zscore(close,_))))",
    "rank(multiply(ts_zscore(volume,_),ts_zscore(close,_)))",
    "rank(ts_decay_linear(reverse(multiply(ts_zscore(volume,_),ts_returns(close,_))),_))",
    # Price-volume correlation (correlation is unitless)
    "rank(reverse(ts_corr(close,volume,_)))",
    "rank(ts_corr(close,volume,_))",
    "rank(ts_decay_linear(reverse(ts_corr(close,volume,_)),_))",
    "rank(ts_decay_linear(ts_corr(close,volume,_),_))",
    "rank(reverse(ts_corr(returns,volume,_)))",
    "rank(ts_corr(returns,volume,_))",
    # Idio-vol / mean-reversion (vol of returns is unitless)
    "rank(reverse(multiply(ts_std_dev(returns,_),ts_returns(close,_))))",
    "rank(multiply(ts_std_dev(returns,_),ts_returns(close,_)))",
    "rank(ts_decay_linear(reverse(ts_std_dev(returns,_)),_))",
    "rank(reverse(ts_std_dev(returns,_)))",
    # Z-score / Bollinger style (z-score of price is unitless)
    "rank(reverse(ts_zscore(close,_)))",
    "rank(reverse(ts_zscore(returns,_)))",
    "rank(ts_zscore(returns,_))",
    "rank(ts_decay_linear(reverse(ts_zscore(close,_)),_))",
    # Microstructure: relative VWAP / close (ratios are unitless)
    "rank(divide(close,vwap))",
    "rank(reverse(divide(close,vwap)))",
    "rank(divide(close,ts_mean(close,_)))",
    "rank(reverse(divide(close,ts_mean(close,_))))",
    "rank(divide(close,ts_max(close,_)))",
    "rank(reverse(divide(close,ts_max(close,_))))",
    "rank(divide(ts_min(close,_),close))",
    "rank(divide(subtract(high,low),close))",
    "rank(reverse(divide(subtract(high,low),close)))",
    # ts_rank (rank in window is unitless)
    "rank(reverse(ts_rank(close,_)))",
    "rank(ts_rank(volume,_))",
    "rank(reverse(ts_rank(volume,_)))",
    "rank(reverse(multiply(ts_rank(volume,_),ts_rank(close,_))))",
    # adv20-relative: volume / adv20 — both share-units → ratio unitless
    "rank(reverse(divide(volume,adv20)))",
    "rank(divide(volume,adv20))",
    "rank(reverse(multiply(divide(volume,adv20),ts_returns(close,_))))",
    # Long-window smoothed signals
    "rank(ts_decay_linear(reverse(ts_returns(close,_)),_))",
    "rank(ts_decay_linear(ts_returns(close,_),_))",
    "rank(ts_decay_linear(reverse(ts_delta(close,_)),_))",
    "rank(ts_decay_linear(divide(close,ts_mean(close,_)),_))",
]

SETTING_VARIANTS = [
    {"neutralization": "INDUSTRY",    "decay": 8,  "truncation": 0.08, "universe": "TOP3000"},
    {"neutralization": "INDUSTRY",    "decay": 16, "truncation": 0.08, "universe": "TOP3000"},
    {"neutralization": "SUBINDUSTRY", "decay": 8,  "truncation": 0.08, "universe": "TOP3000"},
    {"neutralization": "SECTOR",      "decay": 8,  "truncation": 0.08, "universe": "TOP3000"},
    {"neutralization": "INDUSTRY",    "decay": 8,  "truncation": 0.05, "universe": "TOP3000"},
    {"neutralization": "INDUSTRY",    "decay": 8,  "truncation": 0.08, "universe": "TOP1000"},
]

WINDOW_PRESETS = [
    {"short": 5,  "med": 20, "long": 40},
    {"short": 10, "med": 30, "long": 60},
    {"short": 5,  "med": 15, "long": 30},
    {"short": 20, "med": 40, "long": 60},
]

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "delay":          1,
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "pasteurization": "ON",
    "testPeriod":     "P0Y0M",
}


def _load_module(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def expand_template(t: str, win: dict, rng: random.Random) -> str:
    """Replace `_` placeholders with cycling windows from `win`."""
    def repl(m):
        # Sample one of small/med/long for variety
        return str(rng.choice([win["short"], win["med"], win["long"]]))
    return re.sub(r"(?<![A-Za-z0-9_])_(?![A-Za-z0-9_])", repl, t)


def structural_signature(expr: str) -> str:
    out = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isdigit() and (i == 0 or not (expr[i-1].isalnum() or expr[i-1] == "_")):
            k = i
            while k < n and (expr[k].isdigit() or expr[k] == "."):
                k += 1
            tok = expr[i:k]
            if "." not in tok:
                out.append("_")
            else:
                out.append(tok)
            i = k
        else:
            out.append(ch)
            i += 1
    return re.sub(r"\s+", "", "".join(out))


@dataclass
class WQResult:
    eid: int
    template: str
    expression: str
    structural_sig: str
    settings: dict
    ok: bool
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    alpha_id: str = ""
    error: str = ""
    elapsed_s: float = 0.0
    survivor: bool = False


_results_lock = threading.Lock()


def submit_one(session, eid: int, template: str, expression: str,
               settings_extra: dict) -> WQResult:
    full_settings = dict(FIXED_SETTINGS)
    full_settings.update(settings_extra)
    body = {"type": "REGULAR", "settings": full_settings, "regular": expression}

    sig = structural_signature(expression)
    t0 = time.time()

    # POST with 429 backoff
    r = None
    for attempt in range(5):
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   [{eid}] 429; sleep {wait:.0f}s")
            time.sleep(wait)
            continue
        break
    if r is None or r.status_code != 201:
        return WQResult(eid=eid, template=template, expression=expression,
                        structural_sig=sig, settings=full_settings, ok=False,
                        error=f"submit-{getattr(r,'status_code','none')}: "
                              f"{getattr(r,'text','')[:200]}",
                        elapsed_s=time.time() - t0)
    progress_url = r.headers.get("Location")
    if not progress_url:
        return WQResult(eid=eid, template=template, expression=expression,
                        structural_sig=sig, settings=full_settings, ok=False,
                        error="no Location header",
                        elapsed_s=time.time() - t0)

    # Poll
    deadline = t0 + 600
    while time.time() < deadline:
        time.sleep(5)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st == "COMPLETE":
            alpha_id = data.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                              timeout=30)
            if ra.status_code != 200:
                return WQResult(eid=eid, template=template, expression=expression,
                                structural_sig=sig, settings=full_settings,
                                ok=False, alpha_id=alpha_id or "",
                                error=f"alpha-get-{ra.status_code}",
                                elapsed_s=time.time() - t0)
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            checks_pass = sum(1 for c in checks if c.get("result") == "PASS")
            sharpe = float(isb.get("sharpe") or 0.0)
            turnover = float(isb.get("turnover") or 0.0)
            survivor = (sharpe > IS_SH_FLOOR
                         and turnover < IS_TO_CEIL
                         and checks_pass == len(checks))
            return WQResult(
                eid=eid, template=template, expression=expression,
                structural_sig=sig, settings=full_settings, ok=True,
                sharpe=sharpe, turnover=turnover,
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                longCount=int(isb.get("longCount") or 0),
                shortCount=int(isb.get("shortCount") or 0),
                checks_passed=checks_pass, checks_total=len(checks),
                alpha_id=alpha_id or "", elapsed_s=time.time() - t0,
                survivor=survivor,
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return WQResult(eid=eid, template=template, expression=expression,
                            structural_sig=sig, settings=full_settings,
                            ok=False, error=f"sim-{st}: {data.get('message','')[:200]}",
                            elapsed_s=time.time() - t0)
    return WQResult(eid=eid, template=template, expression=expression,
                    structural_sig=sig, settings=full_settings, ok=False,
                    error="poll-timeout", elapsed_s=time.time() - t0)


def candidate_stream(seed: int):
    """Generate (template, expression, settings) tuples indefinitely."""
    rng = random.Random(seed)
    eid = 0
    # Phase 1: each template × first 2 setting variants × 1 window preset
    for s_var in SETTING_VARIANTS[:2]:
        for win in WINDOW_PRESETS[:2]:
            for t in TEMPLATES:
                eid += 1
                expr = expand_template(t, win, rng)
                yield (eid, t, expr, s_var)
    # Phase 2: random sampling unbounded
    while True:
        eid += 1
        t = rng.choice(TEMPLATES)
        win = rng.choice(WINDOW_PRESETS)
        s_var = rng.choice(SETTING_VARIANTS)
        expr = expand_template(t, win, rng)
        yield (eid, t, expr, s_var)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=4,
                     help="Number of structurally distinct WQ survivors")
    ap.add_argument("--max", type=int, default=300,
                     help="Hard cap on submissions")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20260511)
    args = ap.parse_args()

    cm_mod = _load_module(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"Authenticated as {cm.credentials.username}")

    out_path = SDIR / "wq_results.json"
    survivors_path = SDIR / "wq_survivors.json"

    all_results: list[WQResult] = []
    distinct_survivors: dict[str, WQResult] = {}
    seen_exprs: set[str] = set()
    submitted = 0
    started = time.time()

    stream = candidate_stream(args.seed)
    pending: list = []  # list of (future, eid, expression)

    def schedule_one():
        nonlocal submitted
        while True:
            eid, template, expression, settings_extra = next(stream)
            if expression in seen_exprs:
                continue
            seen_exprs.add(expression)
            submitted += 1
            log.info(f"=== [{eid}] submitted #{submitted} | "
                     f"{settings_extra.get('neutralization')[:6]} d={settings_extra.get('decay')} "
                     f"u={settings_extra.get('universe')} | {expression[:80]}")
            return ex.submit(submit_one, cm.session, eid, template,
                              expression, settings_extra)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        # Prime the pool
        for _ in range(args.workers):
            if submitted >= args.max:
                break
            pending.append(schedule_one())

        while pending and len(distinct_survivors) < args.target:
            for fut in as_completed(pending):
                pending.remove(fut)
                try:
                    r: WQResult = fut.result()
                except Exception as exc:
                    log.warning(f"   future raised: {exc}")
                    if submitted < args.max:
                        pending.append(schedule_one())
                    break
                all_results.append(r)
                if r.ok:
                    if r.survivor:
                        sig = r.structural_sig
                        prev = distinct_survivors.get(sig)
                        if prev is None or r.sharpe > prev.sharpe:
                            distinct_survivors[sig] = r
                            log.info(f"   *** SURVIVOR #{len(distinct_survivors)}/{args.target} "
                                     f"sh={r.sharpe:+.3f} to={r.turnover:.3f} fit={r.fitness:+.3f} "
                                     f"checks={r.checks_passed}/{r.checks_total} "
                                     f"alpha_id={r.alpha_id} | {r.expression}")
                    else:
                        log.info(f"   [{r.eid}] sh={r.sharpe:+.3f} to={r.turnover:.3f} "
                                 f"checks={r.checks_passed}/{r.checks_total} "
                                 f"({r.elapsed_s:.0f}s)")
                else:
                    log.info(f"   [{r.eid}] ERR: {r.error[:140]} ({r.elapsed_s:.0f}s)")

                # Persist after every result
                with _results_lock:
                    with open(out_path, "w") as f:
                        json.dump({
                            "submitted": submitted,
                            "elapsed_s": time.time() - started,
                            "n_distinct_survivors": len(distinct_survivors),
                            "target": args.target,
                            "all_results": [asdict(rr) for rr in all_results],
                            "distinct_survivors": [asdict(v) for v in distinct_survivors.values()],
                        }, f, indent=2)
                    with open(survivors_path, "w") as f:
                        json.dump([asdict(v) for v in distinct_survivors.values()], f, indent=2)

                if len(distinct_survivors) >= args.target:
                    log.info(f"Reached target of {args.target} distinct survivors; stopping")
                    break
                if submitted >= args.max:
                    log.info(f"Reached max submissions {args.max}")
                    break
                # Refill pool
                pending.append(schedule_one())
                break  # go back to as_completed loop

    # Final summary
    print()
    print("=" * 110)
    print(f"Submitted: {submitted}  Elapsed: {(time.time()-started)/60:.1f} min")
    print(f"Distinct survivors: {len(distinct_survivors)}/{args.target}")
    print()
    if distinct_survivors:
        print(f"{'rank':<5}{'WQ_SH':>8}{'WQ_TO':>8}{'FIT':>8}{'checks':>8}  alpha_id   expression")
        for i, r in enumerate(sorted(distinct_survivors.values(),
                                      key=lambda r: r.sharpe, reverse=True), 1):
            print(f"{i:<5}{r.sharpe:8.3f}{r.turnover:8.3f}{r.fitness:8.3f}"
                  f" {r.checks_passed}/{r.checks_total:<5}  "
                  f"{r.alpha_id:<10} {r.expression}")
    print("=" * 110)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
