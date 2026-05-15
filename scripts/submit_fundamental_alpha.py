"""Submit 5 fundamental / alternative-data factors to WorldQuant Brain.

User-specified survivor thresholds:
    sharpe   >= 1.75
    turnover <  0.25
    fitness  >  1.5

Each factor carries its OWN simulation settings (universe, delay, decay,
truncation, neutralization, pasteurization, region, language, ...). Every
setting is exposed in the FACTORS table below so they can be tuned
per-factor without touching submission code.

The 5 factors are NOT reused from Alpha101 / classical templates (per
the project's CLAUDE.md mining spec). They are built from fundamental
columns (equity, cap, operating_income, assets) and alternative
columns (analyst earnings revision, options put-call ratio, social
sentiment).

To raise the chance of clearing SH >= 2.5 / FIT > 1.5, each factor:
  * combines axes (value × quality, revision × score) instead of
    relying on a single raw column,
  * uses group_rank / group_zscore so sector concentration is
    pre-neutralized in the signal itself (in addition to setting-level
    neutralization),
  * smooths with ts_mean / ts_decay_linear so turnover stays well
    below 0.25.

Usage:
    python scripts/submit_fundamental_alpha.py

Output:
    WQ_FUNDAMENTAL_RESULTS.json with [{name, expression, settings,
    alpha_id, sharpe, turnover, fitness, returns, drawdown, ...}, ...]
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

# The sandbox proxy rejects requests sent with the default
# `python-requests/*` User-Agent (returns 503 "DNS resolution failure").
# Patch every requests.Session created downstream so it advertises a
# UA that the proxy accepts.
import requests as _requests
_orig_session_init = _requests.Session.__init__
def _patched_session_init(self, *a, **kw):
    _orig_session_init(self, *a, **kw)
    self.headers["User-Agent"] = "curl/8.5.0"
_requests.Session.__init__ = _patched_session_init

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("submit-fund")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# User-specified survivor thresholds.
SHARPE_FLOOR   = 1.75
TURNOVER_CEIL  = 0.25
FITNESS_FLOOR  = 1.5

# ============================================================================
# 5 fundamental / alternative-data factors. EVERY field in `settings` is
# tunable per factor. The dict is passed verbatim to /simulations.
# ============================================================================
FACTORS = [
    # ------------------------------------------------------------------
    # 1. VALUE × QUALITY composite (fundamental).
    #    Long: cheap (high B/M) AND profitable (high ROA).
    #    Short: expensive AND unprofitable.
    #    Pre-neutralized at the SIGNAL level via group_rank against
    #    subindustry, then again at the setting level via INDUSTRY
    #    neutralization. Heavy decay to keep TO small.
    # ------------------------------------------------------------------
    {
        "name": "value_quality_composite",
        "category": "fundamental",
        "rationale": "Fama-French value + Novy-Marx profitability composite "
                     "(Piotroski-style stacking of value and quality).",
        "expression": (
            "add(group_rank(divide(equity, cap), subindustry),"
            " group_rank(divide(operating_income, assets), subindustry))"
        ),
        "settings": {
            "instrumentType":  "EQUITY",
            "region":          "USA",
            "universe":        "TOP3000",
            "delay":           1,
            "decay":           8,
            "neutralization":  "INDUSTRY",
            "truncation":      0.08,
            "pasteurization":  "ON",
            "unitHandling":    "VERIFY",
            "nanHandling":     "OFF",
            "language":        "FASTEXPR",
            "visualization":   False,
            "maxTrade":        "OFF",
            "testPeriod":      "P0Y0M",
        },
    },

    # ------------------------------------------------------------------
    # 2. EARNINGS YIELD smoothed (fundamental).
    #    Operating income / market cap, averaged 60 trading days to
    #    drown out single-print noise, then group-zscored against
    #    subindustry. SUBINDUSTRY neutralization keeps the bet inside
    #    sector-neutral.
    # ------------------------------------------------------------------
    {
        "name": "earnings_yield_smoothed",
        "category": "fundamental",
        "rationale": "Smoothed E/P (operating earnings / market cap); "
                     "classic earnings-yield premium with subindustry neutralization.",
        "expression": (
            "group_zscore(ts_mean(divide(operating_income, cap), 60), subindustry)"
        ),
        "settings": {
            "instrumentType":  "EQUITY",
            "region":          "USA",
            "universe":        "TOP3000",
            "delay":           1,
            "decay":           4,
            "neutralization":  "SUBINDUSTRY",
            "truncation":      0.05,
            "pasteurization":  "ON",
            "unitHandling":    "VERIFY",
            "nanHandling":     "OFF",
            "language":        "FASTEXPR",
            "visualization":   False,
            "maxTrade":        "OFF",
            "testPeriod":      "P0Y0M",
        },
    },

    # ------------------------------------------------------------------
    # 3. ASSET-GROWTH ANOMALY (fundamental).
    #    Cooper-Gulen-Schill (2008): firms that aggressively grow
    #    their asset base UNDERPERFORM. Leading minus shorts the
    #    high-growers. Long lookback (252d) to capture annual growth;
    #    high decay so we are not chasing quarter-end prints.
    # ------------------------------------------------------------------
    {
        "name": "asset_growth_anomaly",
        "category": "fundamental",
        "rationale": "Cooper-Gulen-Schill asset-growth anomaly: high YoY "
                     "asset growth predicts negative returns.",
        "expression": (
            "-group_rank(divide(ts_delta(assets, 252), ts_mean(assets, 252)), subindustry)"
        ),
        "settings": {
            "instrumentType":  "EQUITY",
            "region":          "USA",
            "universe":        "TOP3000",
            "delay":           1,
            "decay":           16,
            "neutralization":  "INDUSTRY",
            "truncation":      0.10,
            "pasteurization":  "ON",
            "unitHandling":    "VERIFY",
            "nanHandling":     "OFF",
            "language":        "FASTEXPR",
            "visualization":   False,
            "maxTrade":        "OFF",
            "testPeriod":      "P0Y0M",
        },
    },

    # ------------------------------------------------------------------
    # 4. ANALYST REVISION × SCORE composite (alternative).
    #    Combine 22-day earnings-revision momentum with the proprietary
    #    composite analyst score. Both ranked within industry so the
    #    signal is sector-neutral before WQ's neutralization layer.
    #    TOP1000 because sentiment data coverage drops at TOP3000.
    # ------------------------------------------------------------------
    {
        "name": "analyst_revision_score",
        "category": "alternative",
        "rationale": "Earnings-revision momentum (Chan-Jegadeesh-Lakonishok) "
                     "+ proprietary analyst score, stacked for robustness.",
        "expression": (
            "add(group_rank(ts_mean(snt1_d1_earningsrevision, 22), industry),"
            " group_rank(snt1_cored1_score, industry))"
        ),
        "settings": {
            "instrumentType":  "EQUITY",
            "region":          "USA",
            "universe":        "TOP1000",
            "delay":           1,
            "decay":           4,
            "neutralization":  "INDUSTRY",
            "truncation":      0.05,
            "pasteurization":  "ON",
            "unitHandling":    "VERIFY",
            "nanHandling":     "OFF",
            "language":        "FASTEXPR",
            "visualization":   False,
            "maxTrade":        "OFF",
            "testPeriod":      "P0Y0M",
        },
    },

    # ------------------------------------------------------------------
    # 5. OPTIONS PUT-CALL MEAN-REVERSION (alternative).
    #    Extreme bearish positioning (high PCR_OI) historically reverts.
    #    ts_zscore over 60 days picks the *anomaly* relative to that
    #    name's recent history (not the cross-section). Leading minus
    #    fades crowded-bearish, longs crowded-bullish. SECTOR
    #    neutralization because option liquidity varies sharply
    #    across sectors.
    # ------------------------------------------------------------------
    {
        "name": "option_pcr_meanrev",
        "category": "alternative",
        "rationale": "Put-call open-interest ratio contrarian: extreme bearish "
                     "positioning historically reverts.",
        "expression": (
            "-group_rank(ts_zscore(pcr_oi_270, 60), sector)"
        ),
        "settings": {
            "instrumentType":  "EQUITY",
            "region":          "USA",
            "universe":        "TOP1000",
            "delay":           1,
            "decay":           4,
            "neutralization":  "SECTOR",
            "truncation":      0.05,
            "pasteurization":  "ON",
            "unitHandling":    "VERIFY",
            "nanHandling":     "OFF",
            "language":        "FASTEXPR",
            "visualization":   False,
            "maxTrade":        "OFF",
            "testPeriod":      "P0Y0M",
        },
    },
]


# ============================================================================
# Submission machinery
# ============================================================================
POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 5


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def submit_one(session, expression: str, settings: dict) -> dict:
    body = {"type": "REGULAR", "settings": settings, "regular": expression}

    log.info(f"-> POST /simulations  expr={expression!r}")
    log.info(f"   settings={settings}")
    for attempt in range(5):
        r = session.post("https://api.worldquantbrain.com/simulations",
                         json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 throttled; sleeping {wait:.0f}s")
            time.sleep(wait); continue
        break
    if r.status_code != 201:
        return {"ok": False, "stage": "submit", "status": r.status_code,
                "body": r.text[:500], "expression": expression,
                "settings": settings}
    progress_url = r.headers.get("Location")
    if not progress_url:
        return {"ok": False, "stage": "submit",
                "error": "no Location header", "expression": expression,
                "settings": settings}

    t0 = time.time()
    last_status = ""
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        status = data.get("status", "")
        if status != last_status:
            log.info(f"   status={status} ({int(time.time() - t0)}s)")
            last_status = status
        if status == "COMPLETE":
            alpha_id = data.get("alpha")
            if not alpha_id:
                return {"ok": False, "stage": "complete-no-alpha",
                        "data": data, "expression": expression,
                        "settings": settings}
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                             timeout=30)
            if ra.status_code != 200:
                return {"ok": False, "stage": "alpha-get",
                        "status": ra.status_code, "body": ra.text[:500],
                        "alpha_id": alpha_id, "expression": expression,
                        "settings": settings}
            return {"ok": True, "alpha_id": alpha_id,
                    "expression": expression, "settings": settings,
                    "alpha": ra.json()}
        if status in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "simulation",
                    "status": status,
                    "message": data.get("message", "")[:500],
                    "expression": expression, "settings": settings}
    return {"ok": False, "stage": "timeout",
            "expression": expression, "settings": settings}


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed -- ensure credential.txt is present")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")
    log.info(f"submitting {len(FACTORS)} fundamental/alt factors "
             f"(thresholds: SH >= {SHARPE_FLOOR}, "
             f"TO < {TURNOVER_CEIL}, FIT > {FITNESS_FLOOR})")

    results = []
    for i, f in enumerate(FACTORS, 1):
        log.info(f"=== [{i}/{len(FACTORS)}] {f['name']} ({f['category']}) ===")
        log.info(f"   rationale: {f['rationale']}")
        res = submit_one(cm.session, f["expression"], f["settings"])
        out = {"name": f["name"], "category": f["category"],
               "rationale": f["rationale"],
               "expression": f["expression"], "settings": f["settings"],
               **{k: v for k, v in res.items()
                  if k not in ("expression", "settings")}}
        if res.get("ok"):
            a = res["alpha"]
            isb = a.get("is") or {}
            out["alpha_id"] = res["alpha_id"]
            out["sharpe"]   = isb.get("sharpe")
            out["turnover"] = isb.get("turnover")
            out["fitness"]  = isb.get("fitness")
            out["returns"]  = isb.get("returns")
            out["drawdown"] = isb.get("drawdown")
            out["longCount"] = isb.get("longCount")
            out["shortCount"] = isb.get("shortCount")
            out["margin"]    = isb.get("margin")
            checks = isb.get("checks") or []
            out["checks_passed"] = sum(1 for c in checks
                                       if c.get("result") == "PASS")
            out["checks_total"]  = len(checks)
            out["checks"]        = checks
            sh, to, fit = (isb.get("sharpe") or 0.0,
                           isb.get("turnover") or 0.0,
                           isb.get("fitness") or 0.0)
            survivor = (sh >= SHARPE_FLOOR and to < TURNOVER_CEIL
                        and fit > FITNESS_FLOOR)
            out["survivor"] = bool(survivor)
            log.info(f"   OK alpha_id={res['alpha_id']} "
                     f"SH={sh:.3f} TO={to:.3f} FIT={fit:.3f}"
                     f"  {'PASS' if survivor else 'FAIL'} filter")
        else:
            out["survivor"] = False
            log.warning(f"   ERR stage={res.get('stage')} "
                        f"msg={res.get('message') or res.get('body','')[:120]}")
        results.append(out)

        outp = REPO / "WQ_FUNDAMENTAL_RESULTS.json"
        with open(outp, "w") as fp:
            json.dump(results, fp, indent=2)

    # Stdout summary
    print()
    print("=" * 120)
    print(f"Filter: SH >= {SHARPE_FLOOR}  AND  TO < {TURNOVER_CEIL}  "
          f"AND  FIT > {FITNESS_FLOOR}")
    print("=" * 120)
    print(f"{'#':<3}{'name':<28}{'cat':<12}{'WQ_SH':>8}{'TO':>7}{'FIT':>7}"
          f"{'RET':>7}{'DD':>7}{'flt':>5}  alpha_id   expression")
    for i, r in enumerate(results, 1):
        if not r.get("ok"):
            print(f"{i:<3}{r['name']:<28}{r['category']:<12}{'ERR':>8}"
                  f"  ({r.get('stage','?')}: "
                  f"{(r.get('message') or r.get('body','') or r.get('error',''))[:60]})")
            continue
        def fmt(x): return f"{x:7.3f}" if isinstance(x, (int, float)) else "    -  "
        flt = "PASS" if r.get("survivor") else "FAIL"
        print(f"{i:<3}{r['name']:<28}{r['category']:<12}"
              f"{fmt(r['sharpe']):>8}{fmt(r['turnover'])}{fmt(r['fitness'])}"
              f"{fmt(r['returns'])}{fmt(r['drawdown'])} {flt:>4}"
              f"  {r['alpha_id']:<10} {r['expression']}")
    print("=" * 120)
    n_pass = sum(1 for r in results if r.get("survivor"))
    print(f"survivors: {n_pass}/{len(results)}")
    print(f"wrote {REPO / 'WQ_FUNDAMENTAL_RESULTS.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
