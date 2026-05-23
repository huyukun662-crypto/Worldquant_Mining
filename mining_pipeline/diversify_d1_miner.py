"""Diversification miner: combine the strongest alpha with signals from
DIFFERENT field families to lower mutual correlation.

Why: WQ Brain's "Submit Alpha" step runs SELF_CORRELATION against the
user's already-submitted pool AND against the active correlation
quarantine. If all 19 of our submit-ready candidates share the same
parent factors (mdl177_* + pv13_revere_index_value), they're highly
correlated and only the first 1-2 will actually pass submission.

To diversify, we combine the current Pareto champion (omnPprj5) with
NEW field families we haven't successfully mined yet:
  - News (high-coverage news_* fields like news_indx_perf, news_eod_close)
  - Socialmedia (scl12_buzz, snt_value)
  - Fundamentals (return_assets, current_ratio)
  - Volume / liquidity (adv20, vwap-based)

The combination form is the same rank-add that worked in combo_d1_miner,
so we're swapping the "B" factor while keeping "A" = omnPprj5.

Run:
    python -m mining_pipeline.diversify_d1_miner
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
log = logging.getLogger("diversify-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

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

# Reigning champion - the SH=2.17 FIT=1.87 expression
CHAMPION = (
    "rank((rank((rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_chg12msip, 120), 20)))"
    " + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_fangma_rvm_usa_fangma_rvm6, 120), 20))))))) "
    "+ (-1 * (rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60))))))"
)


# Diversifying secondary signals - each is a self-contained alpha-ish
# wrap of a field we haven't successfully mined yet. Pairing them with
# CHAMPION should keep the strong base while injecting fresh variance.
B_SIGNALS: list[tuple[str, str]] = [
    # (tag, expression)
    # news family
    ("news_indx_perf_zs22",
     "ts_zscore(ts_backfill(news_indx_perf, 60), 22)"),
    ("news_eod_close_avd",
     "rank(ts_av_diff(ts_backfill(news_eod_close, 60), 22))"),
    ("news_high_exc_zs10",
     "ts_zscore(ts_backfill(news_high_exc_stddev, 60), 10)"),
    # socialmedia
    ("scl12_buzz_zs22",
     "ts_zscore(ts_backfill(scl12_buzz, 60), 22)"),
    ("snt_value_zs22",
     "ts_zscore(ts_backfill(snt_value, 60), 22)"),
    ("snt_buzz_ret_zs10",
     "ts_zscore(ts_backfill(snt_buzz_ret, 60), 10)"),
    # fundamentals
    ("return_assets_rank_neg",
     "-rank(ts_backfill(return_assets, 250))"),
    ("current_ratio_rank",
     "rank(ts_backfill(current_ratio, 250))"),
    # PV / liquidity
    ("vol_adv_ratio",
     "rank(divide(ts_backfill(volume, 5), ts_backfill(adv20, 60)))"),
    ("vwap_close_diff",
     "rank(divide(subtract(vwap, close), close))"),
]


POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 6


@dataclass
class SimResult:
    ok: bool
    expression: str
    settings: dict
    tag: str = ""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="WQ_D1_DIVERSIFY.json")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    log.info(f"diversify scan: {len(B_SIGNALS)} pairings × CHAMPION, "
             f"~{len(B_SIGNALS)*120/60:.0f} min")

    out_path = REPO / args.out
    results: list[SimResult] = []
    for i, (tag, b_expr) in enumerate(B_SIGNALS, 1):
        combo = f"rank(({CHAMPION}) + ({b_expr}))"
        log.info(f"=== diversify {i}/{len(B_SIGNALS)}  [{tag}]")
        log.info(f"   B: {b_expr}")
        r = submit(cm.session, combo, BASE_SETTINGS)
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
    print()
    print("=" * 100)
    print(f"diversify done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    ok.sort(key=lambda r: -r.sharpe)
    for r in ok:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  [{r.tag}]")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
