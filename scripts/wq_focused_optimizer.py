"""Focused setting+decay sweep on the 4-5 strongest base expressions
seen by wq_continuous_miner. These have high SH (+1.1 to +1.7) but
TO over the 0.25 ceiling. Strategy:

- For each base expression, sweep:
    * platform `decay` setting    (8, 16, 32, 64)
    * wrap in ts_decay_linear(., d)  with d ∈ (10, 20, 40)
    * neutralization              (INDUSTRY, SUBINDUSTRY, SECTOR)
    * truncation                  (0.05, 0.08, 0.10)
  This targets pushing TO under 0.25 while keeping SH high.

- 2 worker threads (account concurrency cap).
- Stop when 4 structurally distinct survivors are accumulated.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wqfo")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
SDIR = REPO / "logs" / "20260511_wq_focused_opt"
SDIR.mkdir(parents=True, exist_ok=True)

IS_SH_FLOOR = 1.25
IS_TO_CEIL = 0.25

# Base expressions that scored high SH but high TO in wq_continuous_miner
# (these are the seeds — the optimizer will wrap them in ts_decay_linear
# with various windows and sweep the decay/neutralization/truncation grid).
BASE_EXPRS = [
    # #20: SH=+1.58 TO=0.43
    "rank(reverse(ts_zscore(close,5)))",
    # #21: SH=+1.71 TO=0.62
    "rank(reverse(ts_zscore(returns,40)))",
    # #25: SH=+1.64 TO=0.62
    "rank(reverse(divide(close,vwap)))",
    # #10: SH=+1.12 TO=0.35  -- already closest to passing
    "rank(reverse(ts_corr(close,volume,5)))",
    # #7: joint vol+close z-score reversal SH=+1.17 TO=0.60
    "rank(reverse(multiply(ts_zscore(volume,5),ts_zscore(close,5))))",
]

# Wrap each base in ts_decay_linear with d in this set
DECAY_LINEAR_WINDOWS = [None, 10, 20, 40]

# Platform-side decay sweep (reduces TO via signal smoothing)
DECAY_SETTINGS = [8, 16, 32, 64]

NEUTRALIZATIONS = ["INDUSTRY", "SUBINDUSTRY", "SECTOR"]
TRUNCATIONS = [0.05, 0.08, 0.10]
UNIVERSES = ["TOP3000"]  # focus

FIXED_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "delay": 1,
    "language": "FASTEXPR", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "visualization": False, "maxTrade": "OFF", "pasteurization": "ON",
    "testPeriod": "P0Y0M",
}


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def structural_signature(expr: str) -> str:
    out = []; i = 0; n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isdigit() and (i == 0 or not (expr[i-1].isalnum() or expr[i-1] == "_")):
            k = i
            while k < n and (expr[k].isdigit() or expr[k] == "."): k += 1
            tok = expr[i:k]
            out.append("_" if "." not in tok else tok); i = k
        else:
            out.append(ch); i += 1
    return re.sub(r"\s+", "", "".join(out))


@dataclass
class Result:
    eid: int
    base_idx: int
    base_expr: str
    expression: str
    structural_sig: str
    settings: dict
    decay_wrap: int  # 0 if no wrap
    ok: bool
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    checks_passed: int = 0
    checks_total: int = 0
    alpha_id: str = ""
    error: str = ""
    elapsed_s: float = 0.0
    survivor: bool = False


_lock = threading.Lock()


def submit_one(session, eid: int, base_idx: int, base_expr: str,
               expression: str, settings_extra: dict, decay_wrap: int) -> Result:
    full_settings = dict(FIXED_SETTINGS); full_settings.update(settings_extra)
    body = {"type": "REGULAR", "settings": full_settings, "regular": expression}
    sig = structural_signature(expression); t0 = time.time()

    r = None
    for attempt in range(8):
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   [{eid}] 429; sleep {wait:.0f}s")
            time.sleep(wait); continue
        break
    if r is None or r.status_code != 201:
        return Result(eid=eid, base_idx=base_idx, base_expr=base_expr,
                       expression=expression, structural_sig=sig,
                       settings=full_settings, decay_wrap=decay_wrap, ok=False,
                       error=f"submit-{getattr(r,'status_code','none')}: "
                             f"{getattr(r,'text','')[:200]}",
                       elapsed_s=time.time() - t0)
    progress_url = r.headers.get("Location")
    deadline = t0 + 600
    while time.time() < deadline:
        time.sleep(5)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429: time.sleep(30); continue
        if rp.status_code != 200: continue
        data = rp.json(); st = data.get("status", "")
        if st == "COMPLETE":
            alpha_id = data.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                              timeout=30)
            if ra.status_code != 200:
                return Result(eid=eid, base_idx=base_idx, base_expr=base_expr,
                               expression=expression, structural_sig=sig,
                               settings=full_settings, decay_wrap=decay_wrap,
                               ok=False, alpha_id=alpha_id or "",
                               error=f"alpha-get-{ra.status_code}",
                               elapsed_s=time.time() - t0)
            ay = ra.json(); isb = ay.get("is") or {}; checks = isb.get("checks") or []
            checks_pass = sum(1 for c in checks if c.get("result") == "PASS")
            sh = float(isb.get("sharpe") or 0.0); to = float(isb.get("turnover") or 0.0)
            survivor = (sh > IS_SH_FLOOR and to < IS_TO_CEIL
                         and checks_pass == len(checks))
            return Result(eid=eid, base_idx=base_idx, base_expr=base_expr,
                           expression=expression, structural_sig=sig,
                           settings=full_settings, decay_wrap=decay_wrap, ok=True,
                           sharpe=sh, turnover=to,
                           fitness=float(isb.get("fitness") or 0.0),
                           returns=float(isb.get("returns") or 0.0),
                           drawdown=float(isb.get("drawdown") or 0.0),
                           checks_passed=checks_pass, checks_total=len(checks),
                           alpha_id=alpha_id or "", elapsed_s=time.time() - t0,
                           survivor=survivor)
        if st in ("ERROR", "FAILED", "WARNING"):
            return Result(eid=eid, base_idx=base_idx, base_expr=base_expr,
                           expression=expression, structural_sig=sig,
                           settings=full_settings, decay_wrap=decay_wrap, ok=False,
                           error=f"sim-{st}: {data.get('message','')[:200]}",
                           elapsed_s=time.time() - t0)
    return Result(eid=eid, base_idx=base_idx, base_expr=base_expr,
                   expression=expression, structural_sig=sig,
                   settings=full_settings, decay_wrap=decay_wrap, ok=False,
                   error="poll-timeout", elapsed_s=time.time() - t0)


def candidate_stream():
    """For each base expr × decay_wrap × setting cell, yield one job.
    We interleave across base expressions so we explore all 5 mechanisms
    in parallel rather than exhausting one before starting the next.
    """
    grid = list(itertools.product(DECAY_LINEAR_WINDOWS, DECAY_SETTINGS,
                                   NEUTRALIZATIONS, TRUNCATIONS, UNIVERSES))
    eid = 0
    # Round-robin across base expressions
    for cell in grid:
        for base_idx, base in enumerate(BASE_EXPRS):
            d_wrap, decay_set, neut, trunc, univ = cell
            if d_wrap is None:
                expr = base
            else:
                expr = f"ts_decay_linear({base}, {d_wrap})"
            settings_extra = {"decay": decay_set, "neutralization": neut,
                               "truncation": trunc, "universe": univ}
            eid += 1
            yield (eid, base_idx, base, expr, settings_extra, d_wrap or 0)


def main():
    target = 4; max_subs = 200
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"Authenticated as {cm.credentials.username}")

    out_path = SDIR / "wq_focused_results.json"
    survivors_path = SDIR / "wq_focused_survivors.json"

    all_results: list[Result] = []
    distinct_survivors: dict[str, Result] = {}
    seen_jobs: set[tuple] = set()
    submitted = 0; started = time.time()
    stream = candidate_stream(); pending = []

    def schedule_one():
        nonlocal submitted
        for tup in stream:
            eid, base_idx, base, expr, settings_extra, d_wrap = tup
            key = (expr, settings_extra["decay"], settings_extra["neutralization"],
                   settings_extra["truncation"], settings_extra["universe"])
            if key in seen_jobs: continue
            seen_jobs.add(key); submitted += 1
            log.info(f"=== [{eid}] sub#{submitted} base{base_idx}/dwrap={d_wrap} "
                     f"d={settings_extra['decay']} n={settings_extra['neutralization'][:6]} "
                     f"t={settings_extra['truncation']} | {expr[:90]}")
            return ex.submit(submit_one, cm.session, eid, base_idx, base,
                              expr, settings_extra, d_wrap)
        return None

    with ThreadPoolExecutor(max_workers=2) as ex:
        for _ in range(2):
            if submitted >= max_subs: break
            f = schedule_one()
            if f is None: break
            pending.append(f)

        while pending and len(distinct_survivors) < target:
            for fut in as_completed(pending):
                pending.remove(fut)
                try:
                    r: Result = fut.result()
                except Exception as exc:
                    log.warning(f"   future raised: {exc}")
                    if submitted < max_subs:
                        f = schedule_one()
                        if f is not None: pending.append(f)
                    break
                all_results.append(r)
                if r.ok:
                    if r.survivor:
                        sig = r.structural_sig
                        prev = distinct_survivors.get(sig)
                        if prev is None or r.sharpe > prev.sharpe:
                            distinct_survivors[sig] = r
                            log.info(f"   *** SURVIVOR #{len(distinct_survivors)}/{target} "
                                     f"sh={r.sharpe:+.3f} to={r.turnover:.3f} "
                                     f"fit={r.fitness:+.3f} ck={r.checks_passed}/{r.checks_total} "
                                     f"alpha_id={r.alpha_id} | {r.expression}")
                    else:
                        marker = "  +" if r.sharpe > 1.0 else "   "
                        log.info(f"{marker}[{r.eid}] sh={r.sharpe:+.3f} to={r.turnover:.3f} "
                                 f"ck={r.checks_passed}/{r.checks_total} "
                                 f"({r.elapsed_s:.0f}s)")
                else:
                    log.info(f"   [{r.eid}] ERR: {r.error[:120]} ({r.elapsed_s:.0f}s)")

                with _lock:
                    with open(out_path, "w") as fp:
                        json.dump({"submitted": submitted,
                                   "elapsed_s": time.time() - started,
                                   "n_distinct_survivors": len(distinct_survivors),
                                   "all_results": [asdict(rr) for rr in all_results],
                                   "distinct_survivors": [asdict(v) for v in distinct_survivors.values()]},
                                  fp, indent=2)
                    with open(survivors_path, "w") as fp:
                        json.dump([asdict(v) for v in distinct_survivors.values()],
                                  fp, indent=2)

                if len(distinct_survivors) >= target:
                    log.info(f"Reached target of {target} distinct survivors"); break
                if submitted >= max_subs:
                    log.info(f"Reached max submissions {max_subs}"); break
                f = schedule_one()
                if f is None:
                    log.info("Stream exhausted"); break
                pending.append(f); break

    print()
    print("=" * 110)
    print(f"Submitted: {submitted}  Elapsed: {(time.time()-started)/60:.1f} min")
    print(f"Distinct survivors: {len(distinct_survivors)}/{target}")
    if distinct_survivors:
        print()
        print(f"{'rank':<5}{'WQ_SH':>8}{'WQ_TO':>8}{'FIT':>8}{'ck':>6}  alpha_id   expression")
        for i, r in enumerate(sorted(distinct_survivors.values(),
                                      key=lambda r: r.sharpe, reverse=True), 1):
            print(f"{i:<5}{r.sharpe:8.3f}{r.turnover:8.3f}{r.fitness:8.3f}"
                  f" {r.checks_passed}/{r.checks_total:<3}  "
                  f"{r.alpha_id:<10} {r.expression}")
    print("=" * 110)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
