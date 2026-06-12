"""Compute daily-PnL correlation between alphas, vs cached reference alphas.

Usage:
    python scripts/pnl_corr.py ALPHA_ID [ALPHA_ID ...]

Fetches each alpha's PnL recordset from WQ Brain, diffs the cumulative
series to daily PnL, and prints Pearson correlation against every
reference series cached in cache/pnl/*.json (e.g. GroQl8nG, 58vJ2WZ6).
New alphas are added to the cache so they can serve as references later.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
API = "https://api.worldquantbrain.com"
CACHE = REPO / "cache" / "pnl"


def _session():
    spec = importlib.util.spec_from_file_location(
        "cm", REPO / "vendor/worldquant-miner/core/credential_manager.py")
    cm_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cm_mod)
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    assert cm.authenticate(auto_load=True, auto_prompt=False)
    return cm.session


def fetch_pnl(s, alpha_id: str) -> dict:
    p = CACHE / f"{alpha_id}.json"
    if p.exists():
        return json.load(open(p))
    for _ in range(30):
        r = s.get(f"{API}/alphas/{alpha_id}/recordsets/pnl")
        if r.status_code == 200 and r.text:
            d = r.json()
            CACHE.mkdir(parents=True, exist_ok=True)
            json.dump(d, open(p, "w"))
            return d
        time.sleep(float(r.headers.get("Retry-After") or 5))
    raise RuntimeError(f"pnl fetch failed for {alpha_id}")


def daily(d: dict) -> dict:
    recs = d.get("records") or []
    out = {}
    prev = None
    for row in recs:
        date, cum = row[0], row[1]
        if prev is not None:
            out[date] = cum - prev
        prev = cum
    return out


def corr(a: dict, b: dict) -> float:
    keys = sorted(set(a) & set(b))
    if len(keys) < 50:
        return float("nan")
    xs = [a[k] for k in keys]
    ys = [b[k] for k in keys]
    n = len(keys)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else float("nan")


def main():
    ids = sys.argv[1:]
    if not ids:
        print(__doc__)
        return 1
    s = _session()
    refs = {p.stem: daily(json.load(open(p))) for p in CACHE.glob("*.json")
            if p.stem not in ids}
    for aid in ids:
        try:
            mine = daily(fetch_pnl(s, aid))
        except RuntimeError as e:
            print(f"{aid}: {e}")
            continue
        cors = sorted(((corr(mine, r), name) for name, r in refs.items()),
                      reverse=True)
        tops = "  ".join(f"{name}:{c:.3f}" for c, name in cors)
        print(f"{aid}  {tops}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
