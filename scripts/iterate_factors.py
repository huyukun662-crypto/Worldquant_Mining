"""Iterative WQ Brain mining: push WQ_SH towards 1.75.

Round 1: a batch of stronger composite expressions (multi-axis stacks +
alternative-data overlays). Each entry has its own settings.

Round 2 (manual gating after round 1): sweep settings on the top
expressions from round 1.

Output: WQ_ITERATION_RESULTS.json (appended incrementally so a crash
preserves data).

Usage:
    python scripts/iterate_factors.py --round 1
    python scripts/iterate_factors.py --round 2 --base-expr "<expr>"
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

import requests as _requests
_orig_session_init = _requests.Session.__init__
def _patched_session_init(self, *a, **kw):
    _orig_session_init(self, *a, **kw)
    self.headers["User-Agent"] = "curl/8.5.0"
_requests.Session.__init__ = _patched_session_init

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("iterate")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
OUT = REPO / "WQ_ITERATION_RESULTS.json"

POLL_TIMEOUT_S = 900
POLL_INTERVAL_S = 5

# Survivor floor
SHARPE_FLOOR  = 1.75
TURNOVER_CEIL = 0.25
FITNESS_FLOOR = 1.5


def base_settings(**overrides):
    s = {
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
    }
    s.update(overrides)
    return s


# =====================================================================
# Round 1: stronger composites built from columns with high alphaCount.
# Each combines value/quality/growth/cashflow/analyst axes that the
# literature shows are roughly orthogonal.
# =====================================================================
ROUND_1 = [
    # 1. Triple composite: B/M + ROA + E/P (value + quality + earnings)
    {
        "name": "r1_triple_value_quality_eps",
        "expression": (
            "add(add(group_rank(divide(equity, cap), subindustry),"
            " group_rank(divide(operating_income, assets), subindustry)),"
            " group_rank(divide(income, cap), subindustry))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 2. ROIC: operating_income / (equity + debt)
    {
        "name": "r1_roic_smoothed",
        "expression": (
            "group_zscore(ts_mean(divide(operating_income, add(equity, debt)),"
            " 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 3. FCF yield: (cashflow_op - capex) / cap
    {
        "name": "r1_fcf_yield",
        "expression": (
            "group_zscore(ts_mean(divide(subtract(cashflow_op, capex), cap),"
            " 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 4. Quality × growth: ROA boosted, asset-growth penalized
    {
        "name": "r1_quality_minus_growth",
        "expression": (
            "subtract(group_rank(divide(operating_income, assets), subindustry),"
            " group_rank(divide(ts_delta(assets, 252), ts_mean(assets, 252)),"
            " subindustry))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 5. Gross-margin (Novy-Marx pure): (revenue - cogs) / assets
    {
        "name": "r1_gross_profitability",
        "expression": (
            "group_zscore(ts_mean(divide(subtract(revenue, cogs), assets),"
            " 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 6. EBIT yield (Greenblatt magic-formula style)
    {
        "name": "r1_ebit_yield",
        "expression": (
            "group_zscore(ts_mean(divide(ebit, cap), 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 7. Earnings revision × analyst score × earnings surprise composite
    {
        "name": "r1_analyst_triple",
        "expression": (
            "add(add(group_rank(ts_mean(snt1_d1_earningsrevision, 22), industry),"
            " group_rank(snt1_cored1_score, industry)),"
            " group_rank(snt1_d1_netrecpercent, industry))"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.05, universe="TOP1000"),
    },
    # 8. Mega-stack: value + quality - leverage + earnings yield + (negative) asset growth
    {
        "name": "r1_megastack_5axis",
        "expression": (
            "add(add(add(group_rank(divide(equity, cap), subindustry),"
            " group_rank(divide(operating_income, assets), subindustry)),"
            " group_rank(divide(income, cap), subindustry)),"
            " subtract(group_rank(divide(subtract(revenue, cogs), assets), subindustry),"
            " group_rank(divide(ts_delta(assets, 252), ts_mean(assets, 252)), subindustry)))"
        ),
        "settings": base_settings(decay=16, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
]


# =====================================================================
# Round 3: EBIT-yield base (best of R1, SH=0.62 alone) crossed with
# orthogonal PV axes (momentum 12m, low-vol, short-term reversal).
# Each axis is empirically near-zero correlated with cross-sectional
# value/quality fundamentals, so stacking should add Sharpe.
# =====================================================================
EBIT_YIELD = "group_rank(ts_mean(divide(ebit, cap), 120), subindustry)"
MOM_12M    = "group_rank(ts_sum(returns, 240), subindustry)"
LOWVOL_60D = "-group_rank(ts_std_dev(returns, 60), subindustry)"
SHORT_REV  = "-group_rank(ts_sum(returns, 5), subindustry)"
ROA        = "group_rank(divide(operating_income, assets), subindustry)"

ROUND_3 = [
    # 1. EBIT + 12-month momentum
    {
        "name": "r3_ebit_x_mom12m",
        "expression": f"add({EBIT_YIELD}, {MOM_12M})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 2. EBIT + low-volatility
    {
        "name": "r3_ebit_x_lowvol",
        "expression": f"add({EBIT_YIELD}, {LOWVOL_60D})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 3. EBIT + short-term reversal (1-week)
    {
        "name": "r3_ebit_x_shortrev",
        "expression": f"add({EBIT_YIELD}, {SHORT_REV})",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 4. EBIT + momentum + low-vol (3-axis)
    {
        "name": "r3_ebit_mom_lowvol",
        "expression": f"add(add({EBIT_YIELD}, {MOM_12M}), {LOWVOL_60D})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 5. Full 5-axis stack: value (EBIT) + quality (ROA) + momentum +
    #    low-vol + short-rev
    {
        "name": "r3_full5axis",
        "expression": (f"add(add(add(add({EBIT_YIELD}, {ROA}), {MOM_12M}),"
                       f" {LOWVOL_60D}), {SHORT_REV})"),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 6. Pure PV (no fundamentals): momentum + low-vol + short-rev
    #    -- baseline to see whether fundamentals add anything
    {
        "name": "r3_pure_pv",
        "expression": f"add(add({MOM_12M}, {LOWVOL_60D}), {SHORT_REV})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def submit(session, expression, settings):
    body = {"type": "REGULAR", "settings": settings, "regular": expression}
    log.info(f"-> {expression[:90]}")
    log.info(f"   {settings}")
    # POST with retry on 429 + transient network errors
    r = None
    for attempt in range(5):
        try:
            r = session.post("https://api.worldquantbrain.com/simulations",
                             json=body, timeout=30)
        except _requests.exceptions.RequestException as e:
            log.warning(f"   POST error: {e}; retry {attempt+1}/5 in 10s")
            time.sleep(10); continue
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 30)); continue
        break
    if r is None or r.status_code != 201:
        return {"ok": False, "stage": "submit",
                "status": getattr(r, "status_code", None),
                "body": (r.text[:300] if r is not None else "no response")}
    progress = r.headers.get("Location")
    if not progress:
        return {"ok": False, "stage": "submit", "error": "no Location"}
    t0 = time.time()
    last = ""
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        try:
            rp = session.get(progress, timeout=30)
        except _requests.exceptions.RequestException as e:
            log.warning(f"   poll network error: {type(e).__name__}; retry")
            continue
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        try:
            d = rp.json()
        except ValueError:
            continue
        st = d.get("status", "")
        if st != last:
            log.info(f"   status={st} ({int(time.time()-t0)}s)")
            last = st
        if st == "COMPLETE":
            aid = d.get("alpha")
            try:
                ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}",
                                  timeout=30)
            except _requests.exceptions.RequestException as e:
                return {"ok": False, "stage": "alpha-get-network",
                        "alpha_id": aid, "error": str(e)[:200]}
            if ra.status_code != 200:
                return {"ok": False, "stage": "alpha-get",
                        "status": ra.status_code, "alpha_id": aid}
            return {"ok": True, "alpha_id": aid, "alpha": ra.json()}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "sim", "status": st,
                    "message": (d.get("message") or "")[:300]}
    return {"ok": False, "stage": "timeout"}


def run_batch(session, batch, append_to=None):
    out = list(append_to or [])
    # Skip-resume: a batch member whose (name, expression, settings) is
    # already in `out` is not re-submitted -- preserves R3 progress
    # across crashes / retries.
    done_keys = {(r.get("name"), r.get("expression"),
                  json.dumps(r.get("settings"), sort_keys=True))
                 for r in out if r.get("ok")}
    for i, f in enumerate(batch, 1):
        key = (f["name"], f["expression"],
               json.dumps(f["settings"], sort_keys=True))
        if key in done_keys:
            log.info(f"=== [{i}/{len(batch)}] {f['name']}  [SKIP: already done]")
            continue
        log.info(f"=== [{i}/{len(batch)}] {f['name']} ===")
        try:
            res = submit(session, f["expression"], f["settings"])
        except Exception as e:
            log.error(f"   submit() crashed: {type(e).__name__}: {e}")
            res = {"ok": False, "stage": "exception",
                   "error": f"{type(e).__name__}: {str(e)[:200]}"}
        rec = {"name": f["name"], "expression": f["expression"],
               "settings": f["settings"]}
        if res.get("ok"):
            a = res["alpha"]; isb = a.get("is") or {}
            checks = isb.get("checks") or []
            rec.update({
                "ok": True, "alpha_id": res["alpha_id"],
                "sharpe":   isb.get("sharpe"),
                "turnover": isb.get("turnover"),
                "fitness":  isb.get("fitness"),
                "returns":  isb.get("returns"),
                "drawdown": isb.get("drawdown"),
                "longCount":  isb.get("longCount"),
                "shortCount": isb.get("shortCount"),
                "checks_passed": sum(1 for c in checks if c.get("result") == "PASS"),
                "checks_total":  len(checks),
            })
            sh = rec["sharpe"] or 0.0
            to = rec["turnover"] or 0.0
            fit = rec["fitness"] or 0.0
            rec["survivor"] = bool(sh >= SHARPE_FLOOR and to < TURNOVER_CEIL
                                   and fit > FITNESS_FLOOR)
            log.info(f"   OK alpha={res['alpha_id']} SH={sh:+.3f} "
                     f"TO={to:.3f} FIT={fit:+.3f} "
                     f"{'PASS' if rec['survivor'] else 'fail'}")
        else:
            rec.update({"ok": False, **res, "survivor": False})
            log.warning(f"   ERR {res}")
        out.append(rec)
        with open(OUT, "w") as fp:
            json.dump(out, fp, indent=2)
    return out


def sweep_settings(base_expr: str, base_name: str):
    """Round-2 setting sweep around a base expression."""
    variants = []
    grid = [
        # (decay, neut, trunc, universe)
        ( 4,  "INDUSTRY",     0.05, "TOP3000"),
        ( 8,  "INDUSTRY",     0.10, "TOP3000"),
        (16,  "INDUSTRY",     0.08, "TOP3000"),
        (32,  "INDUSTRY",     0.08, "TOP3000"),
        ( 8,  "SUBINDUSTRY",  0.05, "TOP3000"),
        ( 8,  "SECTOR",       0.05, "TOP3000"),
        ( 8,  "INDUSTRY",     0.05, "TOP1000"),
        ( 8,  "INDUSTRY",     0.05, "TOP500"),
        (16,  "SUBINDUSTRY",  0.05, "TOP1000"),
    ]
    for (decay, neut, trunc, univ) in grid:
        variants.append({
            "name": f"{base_name}_d{decay}_{neut}_t{trunc}_{univ}",
            "expression": base_expr,
            "settings": base_settings(decay=decay, neutralization=neut,
                                       truncation=trunc, universe=univ),
        })
    return variants


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--base-expr", type=str, default="")
    ap.add_argument("--base-name", type=str, default="sweep")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    existing = []
    if OUT.exists():
        existing = json.load(open(OUT))

    if args.round == 1:
        batch = ROUND_1
    elif args.round == 2:
        if not args.base_expr:
            log.error("round 2 needs --base-expr"); return 2
        batch = sweep_settings(args.base_expr, args.base_name)
    elif args.round == 3:
        batch = ROUND_3
    else:
        log.error(f"unknown round {args.round}"); return 2

    log.info(f"round {args.round}: {len(batch)} submissions "
             f"(budget ~{len(batch) * 200 / 60:.0f} min @ ~200s/sim)")
    results = run_batch(cm.session, batch, append_to=existing)

    # Sort by SH desc
    ok = [r for r in results if r.get("ok")]
    ok.sort(key=lambda r: r.get("sharpe") or -99, reverse=True)
    print()
    print("=" * 130)
    print(f"All-time top-10 (Filter: SH >= {SHARPE_FLOOR} AND TO < {TURNOVER_CEIL} AND FIT > {FITNESS_FLOOR}):")
    print("=" * 130)
    print(f"{'#':<3}{'name':<46}{'SH':>7}{'TO':>7}{'FIT':>7}{'flt':>5}  alpha_id   expression")
    for i, r in enumerate(ok[:10], 1):
        sh = r.get('sharpe', 0) or 0
        to = r.get('turnover', 0) or 0
        fit = r.get('fitness', 0) or 0
        flt = "PASS" if r.get("survivor") else "fail"
        print(f"{i:<3}{r['name'][:45]:<46}{sh:7.3f}{to:7.3f}{fit:7.3f} {flt:>4}"
              f"  {r.get('alpha_id','-'):<10} {r['expression'][:60]}")
    print("=" * 130)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
