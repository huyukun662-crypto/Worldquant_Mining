"""Backfill WQ_FUNDAMENTAL_RESULTS.json from /alphas/{id}.

Run after submit_fundamental_alpha.py. Patches any factor whose local
poll timed out by fetching the alpha by id from /users/self/alphas
(matched by expression). Recomputes survivor flags against the current
thresholds.

Usage:
    python scripts/finalize_fundamental_results.py
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

import requests as _requests
_orig_session_init = _requests.Session.__init__
def _patched_session_init(self, *a, **kw):
    _orig_session_init(self, *a, **kw)
    self.headers["User-Agent"] = "curl/8.5.0"
_requests.Session.__init__ = _patched_session_init

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("finalize")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR  = 1.75
TURNOVER_CEIL = 0.25
FITNESS_FLOOR = 1.5


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    inp = REPO / "WQ_FUNDAMENTAL_RESULTS.json"
    data = json.load(open(inp))

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2

    # Fetch the last 30 alphas, build a map by expression to find any
    # that timed out locally but completed on WQ side.
    r = cm.session.get("https://api.worldquantbrain.com/users/self/alphas"
                        "?limit=30&offset=0&order=-dateCreated", timeout=20)
    by_expr: dict[str, dict] = {}
    if r.status_code == 200:
        for a in r.json().get("results", []):
            code = (a.get("regular") or {}).get("code", "")
            if code and code not in by_expr:
                by_expr[code] = a

    for i, rec in enumerate(data):
        if rec.get("ok"):
            sh = rec.get("sharpe") or 0.0
            to = rec.get("turnover") or 0.0
            fit = rec.get("fitness") or 0.0
            rec["survivor"] = bool(sh >= SHARPE_FLOOR and to < TURNOVER_CEIL
                                   and fit > FITNESS_FLOOR)
            continue
        # Try to find by expression
        expr = rec.get("expression", "")
        a = by_expr.get(expr)
        if not a:
            log.info(f"   no match for {rec['name']}")
            continue
        log.info(f"   backfilled {rec['name']} <- {a.get('id')}")
        isb = a.get("is") or {}
        checks = isb.get("checks") or []
        rec.update({
            "ok": True,
            "alpha_id":     a.get("id"),
            "sharpe":       isb.get("sharpe"),
            "turnover":     isb.get("turnover"),
            "fitness":      isb.get("fitness"),
            "returns":      isb.get("returns"),
            "drawdown":     isb.get("drawdown"),
            "longCount":    isb.get("longCount"),
            "shortCount":   isb.get("shortCount"),
            "margin":       isb.get("margin"),
            "checks":       checks,
            "checks_passed": sum(1 for c in checks if c.get("result") == "PASS"),
            "checks_total":  len(checks),
        })
        sh = rec["sharpe"] or 0.0
        to = rec["turnover"] or 0.0
        fit = rec["fitness"] or 0.0
        rec["survivor"] = bool(sh >= SHARPE_FLOOR and to < TURNOVER_CEIL
                               and fit > FITNESS_FLOOR)
        # Clear timeout error indicators
        rec.pop("stage", None)
        rec.pop("error", None)

    with open(inp, "w") as f:
        json.dump(data, f, indent=2)

    # Summary
    print()
    print("=" * 124)
    print(f"Filter: SH >= {SHARPE_FLOOR}  AND  TO < {TURNOVER_CEIL}  "
          f"AND  FIT > {FITNESS_FLOOR}")
    print("=" * 124)
    print(f"{'#':<3}{'name':<28}{'cat':<12}{'WQ_SH':>8}{'TO':>7}{'FIT':>7}"
          f"{'RET':>7}{'DD':>7}{'flt':>6}  alpha_id   expression")
    for i, r in enumerate(data, 1):
        if not r.get("ok"):
            print(f"{i:<3}{r['name']:<28}{r['category']:<12}{'ERR':>8}")
            continue
        def fmt(x): return f"{x:7.3f}" if isinstance(x, (int, float)) else "    -  "
        flt = "PASS" if r.get("survivor") else "FAIL"
        print(f"{i:<3}{r['name']:<28}{r['category']:<12}"
              f"{fmt(r['sharpe']):>8}{fmt(r['turnover'])}{fmt(r['fitness'])}"
              f"{fmt(r['returns'])}{fmt(r['drawdown'])} {flt:>5}"
              f"  {r['alpha_id']:<10} {r['expression']}")
    print("=" * 124)
    n_pass = sum(1 for r in data if r.get("survivor"))
    print(f"survivors: {n_pass}/{len(data)}")
    print(f"wrote {inp}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
