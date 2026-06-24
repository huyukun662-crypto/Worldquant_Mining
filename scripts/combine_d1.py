"""Stage 2: combine sign-corrected base signals into a submittable D1 alpha.

The single-signal sweep in `mine_d1.py` rarely clears Sharpe 1.25 on its
own, but many base signals carry a real |Sharpe| ~ 0.8-1.0 (often with the
WRONG sign, i.e. negative Sharpe -> negate it). Averaging several
sign-corrected, structurally-diverse signals raises Sharpe (diversification)
and lowers max drawdown, while the slow components keep turnover low.

This reads `WQ_D1_LOWTO_REPORT.json`, picks the top-K base signals by
|Sharpe| (deduped by structure), builds:

    composite = rank( add( s1, s2, ... ) )      # s_i = +/- rank(base_i)

submits a few (K, settings) combinations to WQ Brain delay=1, and reports
the submittable survivors (all IS checks PASS, SH>1.25, TO<ceiling).

Usage:
    python scripts/combine_d1.py --report WQ_D1_LOWTO_REPORT.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import re
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("combine-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# reuse the submit machinery + Result dataclass from mine_d1
_spec = importlib.util.spec_from_file_location("mine_d1", REPO / "scripts" / "mine_d1.py")
import sys as _sys
mine_d1 = importlib.util.module_from_spec(_spec); _sys.modules["mine_d1"] = mine_d1
_spec.loader.exec_module(mine_d1)
submit = mine_d1.submit


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _structure_key(expr: str) -> str:
    """Coarse signature: operator names + fields, windows stripped. Used to
    avoid combining two near-identical signals."""
    toks = re.findall(r"[a-z_]+[a-z]", expr)
    return ",".join(t for t in toks if t not in ("rank", "zscore", "winsorize",
                                                  "normalize", "std"))


def pick_components(report: list[dict], k: int, min_abs_sharpe: float,
                    max_turnover: float) -> list[str]:
    """Return up to k sign-corrected `rank(base)` component strings, chosen
    by |Sharpe|, deduped by coarse structure."""
    cands = [r for r in report if r.get("ok")
             and abs(r.get("sharpe", 0.0)) >= min_abs_sharpe
             and r.get("turnover", 9) < max_turnover]
    cands.sort(key=lambda r: abs(r.get("sharpe", 0.0)), reverse=True)
    out, seen = [], set()
    for r in cands:
        key = _structure_key(r["expression"])
        if key in seen:
            continue
        seen.add(key)
        sign = "-" if r["sharpe"] < 0 else ""
        out.append(f"{sign}rank({r['expression']})")
        log.info(f"  component SH={r['sharpe']:+.2f} TO={r['turnover']:.3f} "
                 f"{sign}rank({r['expression'][:60]}...)")
        if len(out) >= k:
            break
    return out


def composite(components: list[str]) -> str:
    expr = components[0]
    for c in components[1:]:
        expr = f"add({expr}, {c})"
    return f"rank({expr})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="WQ_D1_LOWTO_REPORT.json")
    ap.add_argument("--ks", type=int, nargs="+", default=[3, 4, 5, 6])
    ap.add_argument("--min-abs-sharpe", type=float, default=0.5)
    ap.add_argument("--component-max-turnover", type=float, default=0.45,
                    help="turnover ceiling for COMPONENTS (blending+decay "
                         "reduces the composite's turnover below this)")
    ap.add_argument("--max-turnover", type=float, default=0.25,
                    help="turnover ceiling for the final SURVIVOR composite")
    ap.add_argument("--out", default="WQ_D1_COMBINED_REPORT.json")
    args = ap.parse_args()

    report = json.load(open(REPO / args.report))
    if isinstance(report, dict):
        report = report.get("factors", report)

    cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
        base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    # Pool of sign-corrected components (largest K we'll need)
    pool = pick_components(report, max(args.ks), args.min_abs_sharpe,
                           args.component_max_turnover)
    if len(pool) < min(args.ks):
        log.error(f"only {len(pool)} usable components found"); return 1

    # Build candidate composites: for each K, the top-K of the pool; sweep
    # two neutralizations (both good for low drawdown).
    settings_variants = [
        {"universe": "TOP3000", "neutralization": "SUBINDUSTRY", "truncation": 0.08, "decay": 0},
        {"universe": "TOP3000", "neutralization": "INDUSTRY",    "truncation": 0.08, "decay": 4},
    ]
    jobs = []
    for k in args.ks:
        if k > len(pool):
            continue
        expr = composite(pool[:k])
        for s in settings_variants:
            jobs.append((k, expr, s))

    log.info(f"submitting {len(jobs)} composite candidates")
    results = []
    for i, (k, expr, s) in enumerate(jobs, 1):
        log.info(f"=== [{i}/{len(jobs)}] K={k} neut={s['neutralization']} decay={s['decay']}")
        r = submit(cm.session, expr, s)
        rd = mine_d1.asdict(r); rd["K"] = k
        results.append(rd)
        if r.ok:
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                     f"DD={r.drawdown:.3f} checks={r.checks_passed}/{r.checks_total} "
                     f"submittable={r.submittable} fail={r.failed_checks}")
        else:
            log.info(f"   [{r.error[:90]}]")
        with open(REPO / args.out, "w") as f:
            json.dump(results, f, indent=2)
        time.sleep(3)

    survivors = [r for r in results if r["ok"] and r["submittable"]
                 and r["sharpe"] > 1.25 and r["turnover"] < args.max_turnover]
    survivors.sort(key=lambda r: (r["turnover"], abs(r["drawdown"]), -r["sharpe"]))
    print("\n" + "=" * 100)
    print(f"SUBMITTABLE composite survivors: {len(survivors)}")
    for r in survivors:
        print(f"  SH={r['sharpe']:.3f} TO={r['turnover']:.3f} FIT={r['fitness']:.3f} "
              f"DD={r['drawdown']:.3f} K={r['K']} id={r['alpha_id']}")
        print(f"    {r['expression']}")
    print("=" * 100)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
