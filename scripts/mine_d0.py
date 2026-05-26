"""Delay-0 cold-field / cold-operator mining harness for WQ Brain.

Strategy (per user spec, 2026-05-26):
  - ONLY delay=0 alphas.
  - Use COLD data fields (low userCount) -- avoid the crowded PV set.
  - Use COLD operators (ts_backfill, hump, group_rank/neutralize,
    ts_av_diff, jump_decay, trade_when, kth_element, ...).
  - NEVER use the `option` category.
  - Goal: pass the WQ submission `/check` (Sharpe>2.0, Fitness>1.3,
    0.01<TO<0.7, sub-universe>0.01, self-corr<0.7). We do NOT submit;
    we only run `/check` to confirm submittability.

Reads candidate expressions from a batch file (one per line, '#'=comment)
or stdin, submits each to /simulations (delay=0) concurrently, polls,
fetches IS metrics, and writes a ranked JSON report.

Usage:
    python scripts/mine_d0.py batch1.txt --out D0_MINING_REPORT.json
    python scripts/mine_d0.py - < batch.txt
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mine-d0")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# Fixed delay=0 settings. universe / neutralization / decay / truncation
# are part of the search space and overridable per-candidate via a trailing
# `| key=val key=val` on the batch line.
BASE_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 0,
    "decay": 4,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

POLL_TIMEOUT_S = 420
POLL_INTERVAL_S = 5
MAX_CONCURRENT = 3
_throttle = threading.Semaphore(MAX_CONCURRENT)


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_line(line: str):
    """`expr | universe=TOP1000 neutralization=SECTOR decay=8` -> (expr, settings_override)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "|" in line:
        expr, rest = line.split("|", 1)
        override = {}
        for tok in rest.split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                if k in ("decay",):
                    v = int(v)
                elif k in ("truncation",):
                    v = float(v)
                override[k] = v
        return expr.strip(), override
    return line.strip(), {}


def submit_one(session, expression: str, override: dict) -> dict:
    settings = dict(BASE_SETTINGS)
    settings.update(override)
    body = {"type": "REGULAR", "settings": settings, "regular": expression}

    with _throttle:
        # POST with 429 backoff
        for attempt in range(6):
            r = session.post("https://api.worldquantbrain.com/simulations",
                             json=body, timeout=30)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After") or 20)
                time.sleep(wait)
                continue
            if r.status_code == 201:
                break
            return {"ok": False, "stage": "submit", "status": r.status_code,
                    "body": r.text[:300], "expression": expression,
                    "settings": settings}
        else:
            return {"ok": False, "stage": "submit-429", "expression": expression,
                    "settings": settings}

        progress_url = r.headers.get("Location")
        if not progress_url:
            return {"ok": False, "stage": "no-location", "expression": expression,
                    "settings": settings}

        t0 = time.time()
        while time.time() - t0 < POLL_TIMEOUT_S:
            time.sleep(POLL_INTERVAL_S)
            rp = session.get(progress_url, timeout=30)
            if rp.status_code == 429:
                time.sleep(15)
                continue
            if rp.status_code != 200:
                continue
            data = rp.json()
            st = data.get("status", "")
            if st == "COMPLETE":
                aid = data.get("alpha")
                ra = session.get(
                    f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
                if ra.status_code != 200:
                    return {"ok": False, "stage": "alpha-get",
                            "status": ra.status_code, "alpha_id": aid,
                            "expression": expression, "settings": settings}
                isb = ra.json().get("is") or {}
                checks = isb.get("checks") or []
                subuni = next((c.get("value") for c in checks
                               if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), None)
                return {
                    "ok": True, "alpha_id": aid, "expression": expression,
                    "settings": settings,
                    "sharpe": isb.get("sharpe"), "turnover": isb.get("turnover"),
                    "fitness": isb.get("fitness"), "returns": isb.get("returns"),
                    "drawdown": isb.get("drawdown"), "margin": isb.get("margin"),
                    "longCount": isb.get("longCount"),
                    "shortCount": isb.get("shortCount"),
                    "sub_universe_sharpe": subuni,
                    "checks_pass": sum(1 for c in checks if c.get("result") == "PASS"),
                    "checks_total": len(checks),
                }
            if st in ("ERROR", "FAILED", "WARNING"):
                return {"ok": False, "stage": "sim", "status": st,
                        "message": (data.get("message") or "")[:300],
                        "expression": expression, "settings": settings}
        return {"ok": False, "stage": "timeout", "expression": expression,
                "settings": settings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", help="batch file (one expr per line) or '-' for stdin")
    ap.add_argument("--out", default="D0_MINING_REPORT.json")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.batch == "-" else open(args.batch).read()
    cands = [c for c in (parse_line(l) for l in raw.splitlines()) if c]
    log.info(f"{len(cands)} candidates to simulate (delay=0)")

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    results = []
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as ex:
        futs = {ex.submit(submit_one, cm.session, e, o): e for e, o in cands}
        done = 0
        for fut in as_completed(futs):
            res = fut.result()
            done += 1
            with lock:
                results.append(res)
                json.dump(results, open(args.out, "w"), indent=2)
            if res.get("ok"):
                log.info(f"[{done}/{len(cands)}] SH={res['sharpe']} "
                         f"TO={res['turnover']} FIT={res['fitness']} "
                         f"sub={res['sub_universe_sharpe']} :: {res['expression'][:70]}")
            else:
                log.info(f"[{done}/{len(cands)}] ERR {res.get('stage')}/"
                         f"{res.get('status','')} {res.get('message','')[:60]} :: "
                         f"{res['expression'][:60]}")

    ok = [r for r in results if r.get("ok") and r.get("sharpe") is not None]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n" + "=" * 100)
    print(f"{'SH':>7}{'TO':>7}{'FIT':>7}{'subU':>7}{'ret':>7}  alpha_id   expression")
    for r in ok[:40]:
        print(f"{r['sharpe']:7.3f}{r['turnover']:7.3f}{r['fitness']:7.3f}"
              f"{(r['sub_universe_sharpe'] or 0):7.3f}{(r['returns'] or 0):7.3f}  "
              f"{r['alpha_id']:<10} {r['expression'][:64]}")
    print("=" * 100)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
