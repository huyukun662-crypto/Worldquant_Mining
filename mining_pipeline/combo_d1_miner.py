"""Combo D1 miner: rank-sum / multiplicative combos of top-N picks.

Diagnosis of the scan + refine results: 4 model-field candidates topped
Sharpe 1.0-1.3 (PV-only never got close), but their fitness plateaus
near 0.7 because `fitness = SH * sqrt(|returns| / max(TO, 0.125))`. With
returns ~3-7% annual and TO ~0.15-0.24, you can't reach the 1.0 fitness
floor by tuning settings alone. The numerator (returns) is too small.

The classic fix is signal **combination**: average two partially-
uncorrelated top picks. If the rank-correlation between two SH-1.2
signals is ~0.3, the combined alpha gets:
  SH    ~ 1.2 * sqrt(2 / (1 + 0.3)) ~ 1.5
  TO    stays around the higher of the two
  returns scale roughly linearly with SH
  FIT   ~ 1.5 * sqrt(0.06 / 0.20) = 0.82

Three combination forms tested per (A, B) pair:
  1. `rank(A + B)`             - mean-of-ranks (linear blend)
  2. `rank(A * B)`             - amplifies same-sign agreement
  3. `(rank(A) + rank(B)) / 2` - explicit rank-average (no re-ranking)

Top-N pairs sweep -> N*(N-1)/2 pairs. We test the 3 idioms × 1 setting,
so 4 picks gives 6 pairs * 3 idioms = 18 simulations.

Run:
    python -m mining_pipeline.combo_d1_miner --top 4
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from itertools import combinations
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("combo-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
SCAN_PATH = REPO / "WQ_D1_SCAN.json"

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
}

# Settings biased toward the configurations that worked in scan/refine.
COMBO_SETTINGS = {
    "universe":       "TOP3000",
    "neutralization": "INDUSTRY",
    "decay":          8,
    "truncation":     0.05,
}


POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 6


@dataclass
class SimResult:
    ok: bool
    expression: str
    settings: dict
    a_alpha: str = ""
    b_alpha: str = ""
    combo: str = ""
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
    full = dict(FIXED_SETTINGS)
    full.update(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expression}
    for attempt in range(5):
        try:
            r = session.post("https://api.worldquantbrain.com/simulations",
                             json=body, timeout=30)
        except Exception as e:
            log.info(f"   POST exc: {e}; sleep 10"); time.sleep(10); continue
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait); continue
        break
    if r.status_code != 201:
        return SimResult(ok=False, expression=expression, settings=full,
                         error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return SimResult(ok=False, expression=expression, settings=full,
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
                return SimResult(ok=False, expression=expression, settings=full,
                                 alpha_id=alpha_id or "",
                                 error=f"alpha-get-exc: {e}")
            if ra.status_code != 200:
                return SimResult(ok=False, expression=expression, settings=full,
                                 alpha_id=alpha_id or "",
                                 error=f"alpha-get-{ra.status_code}")
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            passed = [c for c in checks if c.get("result") == "PASS"]
            failed = [c for c in checks if c.get("result") == "FAIL"]
            return SimResult(
                ok=True, expression=expression, settings=full,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                checks=checks, checks_passed=len(passed),
                checks_total=len(checks),
                all_checks_pass=(len(failed) == 0 and len(checks) > 0),
                alpha_id=alpha_id or "")
        if st in ("ERROR", "FAILED", "WARNING"):
            return SimResult(ok=False, expression=expression, settings=full,
                             error=f"sim-{st}: {data.get('message','')[:300]}")
    return SimResult(ok=False, expression=expression, settings=full,
                     error="poll-timeout")


def signed_expr(scan_entry: dict) -> str:
    """Return the *positive-Sharpe* form of a scan entry's expression.
    Scan items with negative SH need their sign flipped first."""
    e = scan_entry["expression"]
    if scan_entry["sharpe"] < 0:
        return f"(-1 * ({e}))"
    return e


def build_combos(a: str, b: str) -> list[tuple[str, str]]:
    """Return [(name, expression), ...] for the 3 combination forms."""
    return [
        ("add",   f"rank(({a}) + ({b}))"),
        ("mul",   f"rank(({a}) * ({b}))"),
        ("ravg",  f"add({a}, {b}) / 2"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--out", type=str, default="WQ_D1_COMBO.json")
    args = ap.parse_args()

    if not SCAN_PATH.exists():
        log.error(f"need {SCAN_PATH} from smart_d1_miner --phase scan first")
        return 2
    scan = json.loads(SCAN_PATH.read_text())
    ok = [r for r in scan if r["ok"]]
    ok.sort(key=lambda r: -abs(r["sharpe"]))
    picks = ok[:args.top]
    log.info(f"top {len(picks)} picks chosen by |SH|:")
    for p in picks:
        c = p.get("candidate", {})
        log.info(f"   SH={p['sharpe']:+.2f}  {c.get('idiom','?')}({c.get('field_','?')})")

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / args.out
    results: list[SimResult] = []
    pairs = list(combinations(range(len(picks)), 2))
    total = len(pairs) * 3
    log.info(f"combo sweep: {len(pairs)} pairs × 3 idioms = {total} sims "
             f"(~{total*120/60:.0f} min)")

    counter = 0
    for i, j in pairs:
        a_entry = picks[i]
        b_entry = picks[j]
        a_expr = signed_expr(a_entry)
        b_expr = signed_expr(b_entry)
        for name, expr in build_combos(a_expr, b_expr):
            counter += 1
            log.info(f"=== combo {counter}/{total} [{name}] "
                     f"({a_entry['candidate']['field_'][:30]}, "
                     f"{b_entry['candidate']['field_'][:30]})")
            log.info(f"   expr: {expr[:160]}")
            r = submit(cm.session, expr, COMBO_SETTINGS)
            r.a_alpha = a_entry.get("alpha_id", "")
            r.b_alpha = b_entry.get("alpha_id", "")
            r.combo = name
            if r.ok:
                log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} "
                         f"FIT={r.fitness:+.3f} pass={r.all_checks_pass} "
                         f"({r.checks_passed}/{r.checks_total}) "
                         f"alpha={r.alpha_id}")
            else:
                log.info(f"   ERR: {r.error[:160]}")
            results.append(r)
            out_path.write_text(json.dumps([asdict(x) for x in results], indent=2))

    ok = [r for r in results if r.ok]
    ready = [r for r in ok if r.all_checks_pass]
    ok.sort(key=lambda r: -r.sharpe)
    print()
    print("=" * 110)
    print(f"combo done: {len(ok)}/{len(results)} OK; submit-ready: {len(ready)}")
    for r in ok[:15]:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  "
              f"{r.combo}  {r.expression[:80]}")
    print("=" * 110)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
