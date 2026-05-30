"""Compute daily-PnL correlation between two WQ Brain alphas.

Used to verify a newly-mined D0 factor is UNCORRELATED with an existing
one (e.g. the short-interest winner KPkVxEb1) before treating it as a
genuine diversifier.

Usage:
    python scripts/d0_corr.py <alpha_id_A> <alpha_id_B> [<alpha_id_C> ...]

Fetches /alphas/{id}/recordsets/pnl for each, aligns on date, diffs the
cumulative PnL to daily PnL, and prints the pairwise Pearson correlation
matrix.
"""
from __future__ import annotations

import sys
import time

import d0_mine  # same dir; provides _session() and API


def fetch_pnl(session, alpha_id, timeout=120):
    """Return {date: cumulative_pnl} for an alpha (polls until ready)."""
    url = f"{d0_mine.API}/alphas/{alpha_id}/recordsets/pnl"
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = session.get(url, timeout=30)
        if r.status_code == 429:
            time.sleep(20)
            continue
        if r.status_code == 204 or not r.text.strip():
            time.sleep(5)
            continue
        if r.status_code not in (200, 201):
            raise SystemExit(f"{alpha_id}: HTTP {r.status_code} {r.text[:200]}")
        data = r.json()
        recs = data.get("records") or []
        # schema: records = [[date, pnl], ...]; columns describe order
        cols = [c.get("name") for c in (data.get("schema", {}).get("properties") or [])]
        di = cols.index("date") if "date" in cols else 0
        pi = cols.index("pnl") if "pnl" in cols else 1
        out = {}
        for row in recs:
            out[row[di]] = float(row[pi])
        return out
    raise SystemExit(f"{alpha_id}: pnl not ready after {timeout}s")


def daily(series):
    """Cumulative -> daily increments, keyed by date."""
    dates = sorted(series)
    out = {}
    prev = None
    for d in dates:
        v = series[d]
        if prev is not None:
            out[d] = v - prev
        prev = v
    return out


def pearson(a, b):
    common = sorted(set(a) & set(b))
    if len(common) < 30:
        return float("nan"), len(common)
    xs = [a[d] for d in common]
    ys = [b[d] for d in common]
    n = len(common)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    if vx == 0 or vy == 0:
        return float("nan"), n
    return cov / (vx * vy), n


if __name__ == "__main__":
    ids = sys.argv[1:]
    if len(ids) < 2:
        print(__doc__)
        raise SystemExit(1)
    sess = d0_mine._session()
    pnls = {aid: daily(fetch_pnl(sess, aid)) for aid in ids}
    print(f"{'pair':24} {'corr':>8} {'n_days':>7}")
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            c, n = pearson(pnls[ids[i]], pnls[ids[j]])
            print(f"{ids[i]+' vs '+ids[j]:24} {c:8.3f} {n:7d}")
