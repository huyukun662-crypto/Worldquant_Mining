"""Pairwise PnL correlation between alphas (pure-python, no numpy).

Fetches each alpha's daily cumulative PnL from
/alphas/{id}/recordsets/pnl, differences it to daily PnL, aligns on common
dates, and prints the Pearson correlation matrix. Used to select a set of
mutually LOW-correlated submittable factors.

Usage:
    python scripts/corr_matrix.py <alpha_id> [<alpha_id> ...]
"""
from __future__ import annotations
import json, sys, time, math
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path

API = "https://api.worldquantbrain.com"
REPO = Path(__file__).resolve().parent.parent


def auth():
    u, p = json.load(open(REPO / "credential.txt"))
    s = requests.Session(); s.auth = HTTPBasicAuth(u, p)
    r = s.post(f"{API}/authentication", timeout=20)
    assert r.status_code == 201, (r.status_code, r.text[:200])
    return s


def daily_pnl(s, aid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = s.get(f"{API}/alphas/{aid}/recordsets/pnl", timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 10)); continue
        if r.status_code == 200 and r.text.strip():
            recs = r.json().get("records", [])
            cum = {row[0]: float(row[1]) for row in recs}
            dates = sorted(cum)
            out = {}
            prev = None
            for d in dates:
                if prev is not None:
                    out[d] = cum[d] - cum[prev]
                prev = d
            return out
        time.sleep(float(r.headers.get("Retry-After") or 3))
    return {}


def pearson(a, b):
    n = len(a)
    if n < 2:
        return float("nan")
    ma = sum(a) / n; mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def main(ids):
    s = auth()
    series = {}
    for aid in ids:
        series[aid] = daily_pnl(s, aid)
        print(f"  {aid}: {len(series[aid])} days", flush=True)
    print("\nCorrelation matrix (daily PnL):")
    hdr = "        " + "".join(f"{a[:8]:>9}" for a in ids)
    print(hdr)
    for ai in ids:
        row = f"{ai[:8]:<8}"
        for aj in ids:
            common = sorted(set(series[ai]) & set(series[aj]))
            va = [series[ai][d] for d in common]
            vb = [series[aj][d] for d in common]
            c = pearson(va, vb)
            row += f"{c:>9.2f}"
        print(row)


if __name__ == "__main__":
    main(sys.argv[1:])
