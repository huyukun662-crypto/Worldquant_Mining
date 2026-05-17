"""Tune the volatility-skew × news-shock alpha on WQ Brain.

Base expression (the candidate the user wants tuned)::

    skew = ts_backfill(implied_volatility_call_{T} - implied_volatility_put_{T}, B);
    gate = (ts_backfill(news_pct_{NS}min, B) < {NT}) *
           (ts_rank(abs(news_pct_{NF}min), {RW}) > {RT});
    trade_when(gate, skew, -1)

The original (T=180, B=5, NS=90, NT=1, NF=30, RW=60, RT=0.80,
decay=6, truncation=0.02, neutralization=INDUSTRY, universe=TOP3000)
fails the SELF_CORRELATION check at 0.7486 (cutoff 0.7). To get it
to pass we need either lower self-correlation OR a sufficiently
higher Sharpe (WQ's 10% rule). We sweep both expression knobs and
sim-settings via Optuna TPE.

Run::

    python scripts/tune_volatility_skew.py --trials 30
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
from typing import Any

import optuna

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tune-skew")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

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

# IV tenors actually exposed on this account (USA TOP3000, delay=1)
IV_TENORS = [60, 90, 120, 150, 180, 270, 360]
# news_pct sub-day windows actually exposed
NEWS_FAST_WINDOWS = [10, 30, 60]      # for the abs(news_pct_X) rank gate
NEWS_SLOW_WINDOWS = [60, 90, 120]     # for the ts_backfill(news_pct_X) gate

SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000", "TOP500"],
    "delay":          [1],
    "decay":          [0, 4, 6, 12, 20, 32],
    "truncation":     [0.01, 0.02, 0.05, 0.08],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET", "NONE"],
    "pasteurization": ["ON", "OFF"],
}

POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 5


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render_expression(p: dict) -> str:
    return (
        f"skew = ts_backfill("
        f"implied_volatility_call_{p['iv_tenor']} - "
        f"implied_volatility_put_{p['iv_tenor']}, {p['backfill']});\n"
        f"gate = (ts_backfill(news_pct_{p['news_slow']}min, {p['backfill']}) "
        f"< {p['news_thresh']}) * "
        f"(ts_rank(abs(news_pct_{p['news_fast']}min), {p['rank_win']}) "
        f"> {p['rank_thresh']});\n"
        f"trade_when(gate, skew, -1)"
    )


@dataclass
class TrialResult:
    ok: bool
    params: dict
    settings: dict
    expression: str
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    margin: float = 0.0          # = bps per trade
    longCount: int = 0
    shortCount: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    self_corr: float | None = None
    self_corr_top: list = field(default_factory=list)  # [{id, sharpe, correlation}]
    checks: list = field(default_factory=list)
    alpha_id: str = ""
    error: str = ""


def submit(session, expression: str, settings: dict) -> TrialResult:
    full = dict(FIXED_SETTINGS); full.update(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expression}

    for attempt in range(5):
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait); continue
        break
    if r.status_code != 201:
        return TrialResult(ok=False, params={}, settings=full,
                            expression=expression,
                            error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return TrialResult(ok=False, params={}, settings=full,
                            expression=expression, error="no Location header")

    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st == "COMPLETE":
            alpha_id = data.get("alpha", "")
            ra = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                timeout=30)
            if ra.status_code != 200:
                return TrialResult(ok=False, params={}, settings=full,
                                    expression=expression,
                                    alpha_id=alpha_id,
                                    error=f"alpha-get-{ra.status_code}")
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            self_corr = None
            for c in checks:
                if c.get("name") in ("SELF_CORRELATION", "CORRELATION_SELF"):
                    self_corr = c.get("value")
                    break
            return TrialResult(
                ok=True, params={}, settings=full, expression=expression,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                margin=float(isb.get("margin") or 0.0),
                longCount=int(isb.get("longCount") or 0),
                shortCount=int(isb.get("shortCount") or 0),
                checks_passed=sum(1 for c in checks
                                   if c.get("result") == "PASS"),
                checks_total=len(checks),
                self_corr=self_corr,
                checks=checks,
                alpha_id=alpha_id,
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return TrialResult(ok=False, params={}, settings=full,
                                expression=expression,
                                error=f"sim-{st}: {data.get('message','')[:300]}")
    return TrialResult(ok=False, params={}, settings=full,
                        expression=expression, error="poll-timeout")


def fetch_self_correlation_full(session, alpha_id: str,
                                  wait_until_done: bool = False,
                                  timeout_s: int = 120
                                  ) -> tuple[float | None, list, str]:
    """Like fetch_self_correlation but also returns the top correlated
    alphas as [{id, sharpe, correlation}]."""
    t0 = time.time()
    while True:
        try:
            r = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self",
                timeout=30)
        except Exception as e:
            return None, [], f"ERROR:{e}"
        if r.status_code in (202, 204) or not r.text.strip():
            if not wait_until_done or time.time() - t0 > timeout_s:
                return None, [], "PENDING"
            time.sleep(5); continue
        if r.status_code == 429:
            time.sleep(15); continue
        if r.status_code != 200:
            return None, [], f"ERROR:{r.status_code}"
        try:
            data = r.json()
        except Exception:
            if not wait_until_done or time.time() - t0 > timeout_s:
                return None, [], "PENDING"
            time.sleep(5); continue
        # Real shape: {"schema": {"properties":[{name},...]}, "records":[[...]], "max": x}
        sprops = (data.get("schema") or {}).get("properties") or []
        col = {p["name"]: i for i, p in enumerate(sprops)
                if isinstance(p, dict) and "name" in p}
        recs = data.get("records") or []
        top = []
        for row in recs:
            if isinstance(row, list) and {"id", "correlation", "sharpe"} <= col.keys():
                top.append({
                    "id":          row[col["id"]],
                    "correlation": row[col["correlation"]],
                    "sharpe":      row[col["sharpe"]],
                })
        max_v = data.get("max") if isinstance(data.get("max"), (int, float)) else None
        if max_v is None and top:
            max_v = max((abs(t["correlation"]) for t in top
                          if isinstance(t["correlation"], (int, float))),
                         default=None)
        if max_v is not None:
            return float(max_v), top, "DONE"
        if not wait_until_done or time.time() - t0 > timeout_s:
            return None, [], "PENDING"
        time.sleep(5)


def fetch_self_correlation(session, alpha_id: str,
                             wait_until_done: bool = False,
                             timeout_s: int = 120) -> tuple[float | None, str]:
    """Fetch SELF_CORRELATION check value for an alpha.

    WQ computes SELF_CORRELATION asynchronously — immediately after the
    sim COMPLETE-s the check is in PENDING. The result endpoint is
    `/alphas/{id}/correlations/self` which returns a 202-style payload
    while pending and the actual records once done.

    Returns (max_abs_correlation, status) where status ∈ {"DONE",
    "PENDING", "ERROR"}.
    """
    t0 = time.time()
    while True:
        try:
            r = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self",
                timeout=30)
        except Exception as e:
            return None, f"ERROR:{e}"
        # While pending the API returns an empty body or 202.
        if r.status_code in (202, 204) or not r.text.strip():
            if not wait_until_done or time.time() - t0 > timeout_s:
                return None, "PENDING"
            time.sleep(5)
            continue
        if r.status_code == 429:
            time.sleep(15); continue
        if r.status_code != 200:
            return None, f"ERROR:{r.status_code}"
        try:
            data = r.json()
        except Exception:
            if not wait_until_done or time.time() - t0 > timeout_s:
                return None, "PENDING"
            time.sleep(5); continue
        # Response shape: {"records": [[corr1, corr2, ...], ...],
        #                  "schema": [{"name": "min", ...}, {"name": "max", ...}]}
        # or histogram-style buckets.  Pick the largest |corr| value.
        vals = []
        if isinstance(data, dict):
            recs = data.get("records")
            schema = data.get("schema", {})
            sprops = (schema.get("properties")
                       if isinstance(schema, dict) else None) or []
            if isinstance(recs, list):
                # Try to use schema to find the "max" column
                max_idx = None
                if sprops:
                    for i, p in enumerate(sprops):
                        if isinstance(p, dict) and p.get("name") in ("max",):
                            max_idx = i
                for row in recs:
                    if isinstance(row, list):
                        if max_idx is not None and max_idx < len(row):
                            v = row[max_idx]
                            if isinstance(v, (int, float)):
                                vals.append(v)
                        else:
                            for v in row:
                                if isinstance(v, (int, float)):
                                    vals.append(v)
                    elif isinstance(row, dict):
                        for k in ("max", "correlation", "value"):
                            v = row.get(k)
                            if isinstance(v, (int, float)):
                                vals.append(v)
            for k in ("max", "correlation", "value"):
                v = data.get(k)
                if isinstance(v, (int, float)):
                    vals.append(v)
        if vals:
            return float(max(abs(v) for v in vals)), "DONE"
        # No values - might still be pending under another encoding.
        if not wait_until_done or time.time() - t0 > timeout_s:
            return None, "PENDING"
        time.sleep(5)


def fetch_self_corr_from_checks(session, alpha_id: str) -> tuple[str, float | None]:
    """Re-poll /alphas/{id} for the SELF_CORRELATION check status+value."""
    try:
        ra = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                         timeout=30)
        if ra.status_code != 200:
            return f"ERROR:{ra.status_code}", None
        isb = (ra.json().get("is") or {})
        for c in isb.get("checks", []) or []:
            if c.get("name") == "SELF_CORRELATION":
                return c.get("result", "?"), c.get("value")
        return "MISSING", None
    except Exception as e:
        return f"ERROR:{e}", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", type=str, default="WQ_SKEW_TUNE.json")
    ap.add_argument("--baseline-only", action="store_true",
                     help="Submit the original expression only and exit")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    results: list[TrialResult] = []

    # Always submit the baseline first so we have a known reference point.
    baseline_params = {
        "iv_tenor":    180,
        "backfill":    5,
        "news_slow":   90,
        "news_thresh": 1,
        "news_fast":   30,
        "rank_win":    60,
        "rank_thresh": 0.80,
    }
    baseline_settings = {
        "universe":       "TOP3000",
        "delay":          1,
        "decay":          6,
        "truncation":     0.02,
        "neutralization": "INDUSTRY",
        "pasteurization": "ON",
    }
    expr0 = render_expression(baseline_params)
    log.info("=== BASELINE ===")
    log.info(f"   {expr0!r}")
    r0 = submit(cm.session, expr0, baseline_settings)
    r0.params = baseline_params
    if r0.ok:
        log.info(f"   baseline SH={r0.sharpe:+.3f} TO={r0.turnover:.3f} "
                  f"FIT={r0.fitness:+.3f} "
                  f"checks={r0.checks_passed}/{r0.checks_total}")
    else:
        log.warning(f"   baseline FAILED: {r0.error}")
    results.append(r0)
    with open(args.out, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    if args.baseline_only:
        if r0.ok and r0.alpha_id:
            sc, top, status = fetch_self_correlation_full(
                cm.session, r0.alpha_id, wait_until_done=True, timeout_s=120)
            log.info(f"   baseline self_corr={sc} ({status}) "
                      f"top={top[:3]}")
            r0.self_corr = sc; r0.self_corr_top = top
            with open(args.out, "w") as f:
                json.dump([asdict(r) for r in results], f, indent=2)
        return 0

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=args.seed),
    )

    def objective(trial: optuna.trial.Trial) -> float:
        params = {
            "iv_tenor":    trial.suggest_categorical("iv_tenor", IV_TENORS),
            "backfill":    trial.suggest_int("backfill", 2, 20),
            "news_slow":   trial.suggest_categorical("news_slow",
                                                       NEWS_SLOW_WINDOWS),
            "news_thresh": trial.suggest_categorical("news_thresh", [1, 2]),
            "news_fast":   trial.suggest_categorical("news_fast",
                                                       NEWS_FAST_WINDOWS),
            "rank_win":    trial.suggest_int("rank_win", 20, 180, step=10),
            "rank_thresh": trial.suggest_float("rank_thresh", 0.60, 0.95,
                                                  step=0.05),
        }
        settings = {k: trial.suggest_categorical(k, v)
                     for k, v in SETTING_SPACE.items()}
        expr = render_expression(params)
        log.info(f"=== trial {trial.number+1}/{args.trials} ===")
        log.info(f"   params={params}")
        log.info(f"   settings={settings}")
        res = submit(cm.session, expr, settings)
        res.params = params
        results.append(res)
        # Persist after every trial so we don't lose work on crash.
        with open(args.out, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

        if not res.ok:
            log.info(f"   [{res.error[:100]}]")
            return -10.0

        # Hard constraint: turnover cap per CLAUDE.md.
        penalty = 5.0 if res.turnover >= 0.25 else 0.0
        score = res.sharpe - penalty
        log.info(f"   WQ_SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                  f"FIT={res.fitness:+.3f} "
                  f"checks={res.checks_passed}/{res.checks_total}  "
                  f"score={score:+.3f}")
        return score

    study.optimize(objective, n_trials=args.trials, show_progress_bar=False)

    # Pass 2: poll SELF_CORRELATION for every successful trial.  WQ
    # computes it asynchronously, so by the time we finish the sweep
    # most are ready.  For any still PENDING we wait up to ~60s.
    log.info("=== pass 2: fetching SELF_CORRELATION for each alpha ===")
    for r in results:
        if not r.ok or not r.alpha_id:
            continue
        sc, top, status = fetch_self_correlation_full(
            cm.session, r.alpha_id, wait_until_done=True, timeout_s=90)
        if status != "DONE":
            chk_status, chk_val = fetch_self_corr_from_checks(
                cm.session, r.alpha_id)
            if isinstance(chk_val, (int, float)):
                sc = float(chk_val); status = "DONE"
            log.info(f"   {r.alpha_id} self_corr={sc} ({status}, "
                      f"checks={chk_status})")
        else:
            log.info(f"   {r.alpha_id} self_corr={sc:.4f} "
                      f"top={[(t['id'], round(t['correlation'],3), round(t['sharpe'],2)) for t in top[:3]]}")
        r.self_corr = sc
        r.self_corr_top = top

    # Persist final
    with open(args.out, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    # Summary
    ok = [r for r in results if r.ok]
    ok.sort(key=lambda r: r.sharpe, reverse=True)
    print()
    print("=" * 120)
    print(f"Trials OK: {len(ok)}/{len(results)}")
    # Per WQ rule: self-corr passes if max_corr < 0.7 OR
    # this alpha's Sharpe is at least 10% above the correlated peer's.
    def passes_self_corr(r):
        if r.self_corr is None: return None
        if r.self_corr < 0.70: return True
        # find peer sharpe for the max-corr record
        peer_sh = None
        for t in r.self_corr_top:
            if isinstance(t.get("correlation"), (int, float)) and \
               abs(t["correlation"]) >= r.self_corr - 1e-9:
                peer_sh = t.get("sharpe"); break
        if isinstance(peer_sh, (int, float)) and r.sharpe >= 1.10 * peer_sh:
            return True
        return False
    print(f"{'#':<4}{'SH':>7}{'TO':>7}{'FIT':>7}{'sc':>7} sc_ok{'chk':>7}  "
           "alpha_id   iv  bf nslow nt nfast rw   rt  univ     dcy  tr   neut    pasteur")
    for i, r in enumerate(ok[:30], 1):
        p, s = r.params, r.settings
        sc = f"{r.self_corr:.3f}" if r.self_corr is not None else "  -  "
        sc_ok = passes_self_corr(r)
        sc_ok_s = "  Y  " if sc_ok is True else ("  N  " if sc_ok is False else "  ?  ")
        print(f"{i:<4}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}"
               f"{sc:>7} {sc_ok_s} {r.checks_passed:>3}/{r.checks_total:<2}  "
               f"{r.alpha_id:<10} {p.get('iv_tenor','?'):>3} "
               f"{p.get('backfill','?'):>3} {p.get('news_slow','?'):>5} "
               f"{p.get('news_thresh','?'):>2} {p.get('news_fast','?'):>5} "
               f"{p.get('rank_win','?'):>3} {p.get('rank_thresh','?'):>5.2f} "
               f"{s.get('universe','?'):<8} {s.get('decay','?'):>3} "
               f"{s.get('truncation','?'):>5} {s.get('neutralization','?'):<8} "
               f"{s.get('pasteurization','?')}")
    print("=" * 120)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
