#!/usr/bin/env python3
"""Focused grid search around the call-put IV-spread D0 winner.

Best so far (2026-05-21):
  zscore(ts_mean(IV_call_360 - IV_put_360, 10))  SUBINDUSTRY decay=4 trunc=0.02
  -> SH=1.97 FIT=2.34 TO=0.115, 6/8 checks (only LOW_SHARPE 1.97<2.0 fails;
     SELF_CORRELATION pending). And:
  normalize(ts_decay_linear(IV_call_360 - IV_put_360, 20)) trunc=0.01
  -> SH=2.00 FIT=1.85 TO=0.196, 5/8 (CONCENTRATED_WEIGHT +
     LOW_SUB_UNIVERSE_SHARPE fail).

Goal: find one alpha that is SH>=2.0 AND >=6/8 checks (i.e. the union).
Sweeps wrap x maturity x window x decay x truncation, submits each to WQ,
fetches per-check detail, and writes the union-passers to
WQ_D0_CALLPUT_FOCUS.json. Skips (expr,settings) already in the evolve
archive to avoid paying for cached sims.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from mining_pipeline import wq_pipeline as wp

log = logging.getLogger("focus-callput")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

WRAPS = ("zscore", "scale", "winsorize")          # winsorize needs std arg
MATURITIES = (180, 270, 360, 720)
WINDOWS = (8, 10, 12, 15)
DECAYS = (3, 4, 5)
TRUNCS = (0.015, 0.02, 0.025)
NEUT = "SUBINDUSTRY"


def build_expr(wrap: str, M: int, W: int) -> str:
    spread = f"subtract(implied_volatility_call_{M}, implied_volatility_put_{M})"
    core = f"ts_mean({spread}, {W})"
    if wrap == "winsorize":
        return f"winsorize({core}, std=4)"
    return f"{wrap}({core})"


_SIG_KEYS = ("universe", "delay", "decay", "truncation", "neutralization")
def _sig(expr, s):
    return expr + "|" + "|".join(f"{k}={s.get(k)}" for k in _SIG_KEYS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", default="WQ_D0_EVOLVE_REPORT.json")
    ap.add_argument("--out", default="WQ_D0_CALLPUT_FOCUS.json")
    ap.add_argument("--max", type=int, default=200, help="cap total submissions")
    args = ap.parse_args()

    cm_mod = wp._load(wp.VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    # Load archive signatures + any prior focus results to skip
    done = {}
    for p in (args.archive, args.out):
        fp = REPO / p
        if fp.exists():
            try:
                for d in json.load(open(fp)):
                    if d.get("ok") and d.get("expression"):
                        done[_sig(d["expression"], d["settings"])] = d
            except Exception:
                pass
    log.info(f"{len(done)} (expr,settings) already evaluated — will skip")

    combos = list(itertools.product(WRAPS, MATURITIES, WINDOWS, DECAYS, TRUNCS))
    log.info(f"grid size: {len(combos)} (capped at {args.max})")

    results = []
    if (REPO / args.out).exists():
        try: results = json.load(open(REPO / args.out))
        except Exception: results = []

    submitted = 0
    for wrap, M, W, decay, trunc in combos:
        if submitted >= args.max:
            break
        expr = build_expr(wrap, M, W)
        settings = {"universe": "TOP3000", "delay": 0, "decay": decay,
                    "truncation": trunc, "neutralization": NEUT,
                    "pasteurization": "ON"}
        sig = _sig(expr, settings)
        if sig in done:
            continue
        submitted += 1
        log.info(f"[{submitted}] {wrap} M{M} W{W} d{decay} tr{trunc}")
        res = wp.submit(cm.session, expr, settings)
        if not res.ok:
            log.info(f"   ERR {res.error[:80]}")
            continue
        # fetch per-check detail
        checks = []
        try:
            ra = cm.session.get(f"https://api.worldquantbrain.com/alphas/{res.alpha_id}", timeout=30)
            checks = (ra.json().get("is") or {}).get("checks") or []
        except Exception:
            pass
        fails = [c["name"] for c in checks if c.get("result") == "FAIL"]
        rec = {"ok": True, "alpha_id": res.alpha_id, "expression": expr,
               "settings": settings, "sharpe": res.sharpe, "turnover": res.turnover,
               "fitness": res.fitness, "checks_passed": res.checks_passed,
               "checks_total": res.checks_total, "fails": fails}
        results.append(rec)
        json.dump(results, open(REPO / args.out, "w"), indent=2)
        flag = ""
        if res.sharpe >= 2.0 and res.fitness >= 1.3 and res.turnover < 0.25 and not fails:
            flag = "  <<< FULL PASS (modulo pending self-corr)"
        log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} FIT={res.fitness:+.3f} "
                 f"chk={res.checks_passed}/{res.checks_total} fails={fails}{flag}")

    # Summary
    full = [r for r in results if r["sharpe"]>=2.0 and r["fitness"]>=1.3
            and r["turnover"]<0.25 and not r["fails"]]
    print("="*100)
    print(f"submitted {submitted}; total focus results {len(results)}; FULL-PASS {len(full)}")
    for r in sorted(full, key=lambda x:-x["sharpe"]):
        print(f"  SH={r['sharpe']:.2f} TO={r['turnover']:.3f} FIT={r['fitness']:.2f} "
              f"{r['alpha_id']}  {r['expression']}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
