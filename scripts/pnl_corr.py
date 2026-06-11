"""Compute daily-PnL correlation between WQ alphas.

Usage:
    python scripts/pnl_corr.py REF_ID ID1 ID2 ...
Fetches /alphas/{id}/recordsets/pnl for each, aligns on date, and prints
Pearson correlation of daily PnL *changes* (first differences) between
REF_ID and every other id. WQ's self-correlation is on daily PnL series;
we report both raw-PnL and dPnL correlations.
"""
from __future__ import annotations
import sys, time, json
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
API = "https://api.worldquantbrain.com"


def auth():
    s = requests.Session()
    c = json.loads((REPO / "credential.txt").read_text())
    s.auth = HTTPBasicAuth(c[0], c[1])
    s.post(f"{API}/authentication", timeout=20)
    return s


def pnl(s, aid, tries=20):
    for _ in range(tries):
        r = s.get(f"{API}/alphas/{aid}/recordsets/pnl", timeout=60)
        if r.status_code == 200 and r.text.strip():
            recs = r.json().get("records") or []
            return {row[0]: row[1] for row in recs}
        time.sleep(5)
    return {}


def corr(a: dict, b: dict, diff=True):
    dates = sorted(set(a) & set(b))
    xa = [a[d] for d in dates]; xb = [b[d] for d in dates]
    if diff:
        xa = [xa[i] - xa[i-1] for i in range(1, len(xa))]
        xb = [xb[i] - xb[i-1] for i in range(1, len(xb))]
    n = len(xa)
    if n < 2: return float("nan")
    ma = sum(xa)/n; mb = sum(xb)/n
    cov = sum((xa[i]-ma)*(xb[i]-mb) for i in range(n))
    va = sum((xa[i]-ma)**2 for i in range(n))**0.5
    vb = sum((xb[i]-mb)**2 for i in range(n))**0.5
    return cov/(va*vb) if va and vb else float("nan")


def main():
    ref = sys.argv[1]; others = sys.argv[2:]
    s = auth()
    pref = pnl(s, ref)
    print(f"ref {ref}: {len(pref)} days")
    for aid in others:
        pb = pnl(s, aid)
        c = corr(pref, pb, diff=True)
        craw = corr(pref, pb, diff=False)
        print(f"  {aid}: dPnL_corr={c:+.3f}  rawPnL_corr={craw:+.3f}  ({len(pb)} days)")


if __name__ == "__main__":
    main()
