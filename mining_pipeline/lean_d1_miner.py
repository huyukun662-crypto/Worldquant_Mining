"""Lean D1 miner: concise expressions over obscure fields × obscure operators.

Different angle from smart_d1_miner (model fields + standard idioms) and
combo_d1_miner (rank-add of top picks). This module trades expression
size for novelty:

- Fields: rel_*, pv13_*, and selected mid-tail news_* (alphaCount 300-500,
  userCount <= 300) - relational and post-news features rarely used in
  the proprietary model space.
- Operators: hump, ts_quantile, ts_target_tvr_decay, winsorize,
  group_zscore, days_from_last_change, last_diff_value, kth_element,
  jump_decay, ts_scale - all in the 98-op catalog but appear in very
  few public alphas. ts_target_tvr_decay in particular auto-tunes
  decay to hit a target turnover, directly addressing the fitness
  ceiling we hit with model fields.
- Shape: every candidate is wrap(op(field, params)) - one or two
  operators deep, no nested rank-sums.

Run:
    python -m mining_pipeline.lean_d1_miner --out WQ_D1_LEAN.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lean-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


FIXED_SETTINGS = {
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


# Candidates - each is a concise (op-depth <= 2) expression pairing an
# obscure operator with an obscure field. Argument forms are picked
# carefully: operators whose 2nd arg is keyword-only (e.g. hump's
# `hump = 0.01`) get the keyword form; standard-default args (e.g.
# `winsorize(x, std=4)`) use the positional form vendor templates use.
CANDIDATES: list[tuple[str, str]] = [
    # (tag, expression)

    # hump - keyword-only `hump=` arg; use default by omitting
    ("hump_rel_ret_all",
     "rank(hump(ts_backfill(rel_ret_all, 60)))"),
    ("hump_news_dn",
     "-rank(hump(ts_backfill(news_mins_4_pct_dn, 60)))"),

    # ts_quantile - default gaussian driver; just (x, d)
    ("tsquant_news_up",
     "rank(ts_quantile(ts_backfill(news_mins_4_pct_up, 60), 22))"),
    ("tsquant_news_dn",
     "rank(ts_quantile(ts_backfill(news_mins_4_pct_dn, 60), 22))"),

    # ts_target_tvr_decay - auto-tunes decay for target turnover.
    # All named args -> use keyword form for safety.
    ("ttvr_rel_ret_all",
     "ts_target_tvr_decay(ts_backfill(rel_ret_all, 60), target_tvr=0.1)"),
    ("ttvr_news_20up",
     "ts_target_tvr_decay(ts_backfill(news_mins_20_pct_up, 60), target_tvr=0.1)"),

    # winsorize - positional std arg (vendor templates use this)
    ("wins_news_ton_hi",
     "-rank(winsorize(ts_backfill(news_ton_high, 60), std=3))"),

    # group_zscore - sector-relative
    ("gzs_custretsig",
     "group_zscore(ts_backfill(pv13_custretsig_retsig, 60), sector)"),
    ("gzs_rel_ret",
     "group_zscore(ts_backfill(rel_ret_all, 60), industry)"),
    ("gzs_news_dn",
     "group_zscore(ts_backfill(news_mins_4_pct_dn, 60), sector)"),
    ("gzs_adjfactor",
     "group_zscore(ts_backfill(adjfactor, 60), sector)"),

    # days_from_last_change - 1 arg
    ("dflc_revere_idx",
     "rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"),

    # last_diff_value - 2 args
    ("ldv_rel_num_comp",
     "rank(last_diff_value(ts_backfill(rel_num_comp, 60), 10))"),

    # kth_element - 3 args
    ("kth_news_ton_hi",
     "rank(kth_element(ts_backfill(news_ton_high, 60), 5, 1))"),

    # jump_decay - keyword args for sensitivity/force
    ("jump_news_ton_lo",
     "rank(jump_decay(ts_backfill(news_ton_low, 60), 5))"),

    # ts_scale - 2 positional, defaults the constant
    ("tsscale_rel_ret",
     "rank(ts_scale(ts_backfill(rel_ret_all, 60), 30))"),
]


POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 6


@dataclass
class SimResult:
    ok: bool
    expression: str
    tag: str
    settings: dict
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
    full = dict(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expression}
    for attempt in range(5):
        try:
            r = session.post("https://api.worldquantbrain.com/simulations",
                             json=body, timeout=30)
        except Exception as e:
            log.info(f"   POST exc: {e}; sleep 10"); time.sleep(10); continue
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429; sleep {wait:.0f}s"); time.sleep(wait); continue
        break
    if r.status_code != 201:
        return SimResult(ok=False, expression=expression, tag="", settings=full,
                         error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return SimResult(ok=False, expression=expression, tag="", settings=full,
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
            alpha_id = data.get("alpha")
            try:
                ra = session.get(
                    f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                    timeout=30)
            except Exception as e:
                return SimResult(ok=False, expression=expression, tag="",
                                 settings=full, alpha_id=alpha_id or "",
                                 error=f"alpha-get-exc: {e}")
            if ra.status_code != 200:
                return SimResult(ok=False, expression=expression, tag="",
                                 settings=full, alpha_id=alpha_id or "",
                                 error=f"alpha-get-{ra.status_code}")
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            passed = [c for c in checks if c.get("result") == "PASS"]
            failed = [c for c in checks if c.get("result") == "FAIL"]
            return SimResult(
                ok=True, expression=expression, tag="",
                settings=full,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                checks=checks,
                checks_passed=len(passed),
                checks_total=len(checks),
                all_checks_pass=(len(failed) == 0 and len(checks) > 0),
                alpha_id=alpha_id or "")
        if st in ("ERROR", "FAILED", "WARNING"):
            return SimResult(ok=False, expression=expression, tag="",
                             settings=full,
                             error=f"sim-{st}: {data.get('message','')[:300]}")
    return SimResult(ok=False, expression=expression, tag="", settings=full,
                     error="poll-timeout")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_LEAN.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    log.info(f"lean scan: {len(CANDIDATES)} candidates (obscure × obscure), "
             f"~{len(CANDIDATES)*120/60:.0f} min")

    results: list[SimResult] = []
    out_path = REPO / args.out
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        log.info(f"=== lean {i}/{len(CANDIDATES)}  [{tag}]")
        log.info(f"   expr: {expr}")
        r = submit(cm.session, expr, FIXED_SETTINGS)
        r.tag = tag
        if r.ok:
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                     f"pass={r.all_checks_pass} ({r.checks_passed}/{r.checks_total}) "
                     f"alpha={r.alpha_id}")
        else:
            log.info(f"   ERR: {r.error[:160]}")
        results.append(r)
        out_path.write_text(json.dumps([asdict(x) for x in results], indent=2))

    ok = [r for r in results if r.ok]
    ready = [r for r in ok if r.all_checks_pass]
    ok.sort(key=lambda r: -abs(r.sharpe))
    print()
    print("=" * 100)
    print(f"lean done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}] {r.expression[:60]}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
