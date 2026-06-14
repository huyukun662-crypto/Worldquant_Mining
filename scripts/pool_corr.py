"""Pool-orthogonality scorer for WorldQuant Brain delay-0 candidates.

The Performance Comparison score (the number that decides whether a submitted
alpha ADDS or SUBTRACTS from the user's competition score) is driven by the
candidate's MARGINAL contribution to the already-submitted pool, not its
standalone Sharpe.  A high-Sharpe alpha that is highly correlated with the
existing pool dilutes the score (we observed a -638 Performance Comparison
on a value factor that overlapped the pool's existing sales/cap component).

This tool measures, for each candidate alpha_id, the max |correlation| of its
daily PnL against every alpha already in the submitted pool.  Candidates that
clear the D0 submission bar (SH >= 2.0, FIT >= 1.3) AND have a LOW max-corr to
the pool are the ones that will ADD score.

Usage:
    # 1) build/refresh the pool reference (delay-0 submitted alphas):
    python scripts/pool_corr.py --build-pool
    # 2) score a d0_mine results file against the pool:
    python scripts/pool_corr.py --score /tmp/pq_out.json
"""
import json
import sys
import time
import argparse
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

API = "https://api.worldquantbrain.com"
REPO = Path(__file__).resolve().parent.parent
POOL_CACHE = REPO / "constants" / "delay0_pool_pnl.json"


def auth():
    u, p = json.load(open(REPO / "credential.txt"))
    s = requests.Session()
    s.auth = HTTPBasicAuth(u, p)
    s.post(f"{API}/authentication", timeout=20)
    return s


def get_pnl(s, aid, tries=8):
    """Fetch cumulative daily PnL as {date: cum_pnl}. Empty 200 = still
    generating, so retry honoring Retry-After."""
    for _ in range(tries):
        r = s.get(f"{API}/alphas/{aid}/recordsets/pnl", timeout=60)
        if r.status_code == 200 and r.text.strip():
            return {d: v for d, v in r.json().get("records", [])}
        time.sleep(float(r.headers.get("Retry-After", 2)))
    return {}


def daily(pnl, dates):
    cum = [pnl[d] for d in dates]
    return [cum[i] - cum[i - 1] for i in range(1, len(cum))]


def corr(x, y):
    n = len(x)
    if n == 0:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / ((sxx * syy) ** 0.5) if sxx > 0 and syy > 0 else 0.0


def list_submitted(s, delay=0):
    """All submitted alphas for the given delay."""
    out, offset = [], 0
    while True:
        r = s.get(f"{API}/users/self/alphas",
                  params={"limit": 100, "offset": offset}, timeout=50)
        if r.status_code != 200:
            break
        js = r.json()
        res = js.get("results", [])
        if not res:
            break
        for a in res:
            sub = a.get("dateSubmitted") or a.get("status") == "ACTIVE"
            if sub and a.get("settings", {}).get("delay") == delay:
                out.append(a)
        offset += 100
        if offset >= js.get("count", 0):
            break
    return out


def build_pool(delay=0):
    s = auth()
    alphas = list_submitted(s, delay)
    print(f"delay-{delay} submitted pool: {len(alphas)} alphas")
    pnls = {}
    for a in alphas:
        aid = a["id"]
        p = get_pnl(s, aid)
        if p:
            pnls[aid] = p
            code = (a.get("regular") or {}).get("code", "")
            print(f"  {aid}  {code[:70]}")
    dates = sorted(set.intersection(*[set(v.keys()) for v in pnls.values()]))
    ret = {aid: daily(pnls[aid], dates) for aid in pnls}
    meta = {a["id"]: (a.get("regular") or {}).get("code", "") for a in alphas}
    POOL_CACHE.write_text(json.dumps(
        {"delay": delay, "dates": dates, "returns": ret, "code": meta}))
    print(f"saved {POOL_CACHE} ({len(dates)} dates, {len(ret)} alphas)")


def score(results_path):
    s = auth()
    pool = json.load(open(POOL_CACHE))
    pdates, pret = pool["dates"], pool["returns"]
    # pool daily return keyed by the date it was realized on (pdates[k+1])
    pool_by_date = {pid: {pdates[k + 1]: pr[k] for k in range(len(pr))}
                    for pid, pr in pret.items()}
    rows = json.load(open(results_path))
    out = []
    for r in rows:
        if not r.get("ok"):
            continue
        aid = r["alpha_id"]
        pnl = get_pnl(s, aid)
        cdates = sorted(pnl.keys())
        if len(cdates) < 100:
            continue
        cum = [pnl[d] for d in cdates]
        cret = {cdates[i]: cum[i] - cum[i - 1] for i in range(1, len(cdates))}
        maxc = 0.0
        for pid, pmap in pool_by_date.items():
            shared = [d for d in cret if d in pmap]
            if len(shared) < 100:
                continue
            x = [cret[d] for d in shared]
            y = [pmap[d] for d in shared]
            maxc = max(maxc, abs(corr(x, y)))
        passes = r["sharpe"] >= 2.0 and r["fitness"] >= 1.3
        out.append((r["sharpe"], r["fitness"], r["turnover"], maxc, passes, aid,
                    r["expression"]))
    out.sort(key=lambda x: (x[3]))  # by max-corr ascending
    print(f"\n{'SH':>5} {'FIT':>5} {'TO':>6} {'maxCorr':>8} {'D0':>4}  id")
    for sh, fit, to, mc, ps, aid, e in out:
        tag = "PASS" if ps else " -- "
        star = "  <<< ADD (orthogonal & passes)" if (ps and mc < 0.30) else ""
        print(f"{sh:5.2f} {fit:5.2f} {to:6.3f} {mc:8.2f} {tag:>4}  {aid}{star}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-pool", action="store_true")
    ap.add_argument("--delay", type=int, default=0)
    ap.add_argument("--score", metavar="RESULTS_JSON")
    a = ap.parse_args()
    if a.build_pool:
        build_pool(a.delay)
    elif a.score:
        score(a.score)
    else:
        ap.print_help()
