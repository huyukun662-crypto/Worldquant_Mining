"""Fetch daily PnL series for alphas and compute pairwise correlation.

WQ Brain generates recordsets lazily: GET /alphas/{id}/recordsets/pnl may
return 200 with an empty body and a Retry-After header while the data is
being prepared — poll until the JSON body arrives.

Usage:
    python scripts/wq_corr.py ALPHA_ID1 ALPHA_ID2 [ALPHA_ID3 ...]
Prints the correlation matrix of daily PnL diffs (i.e. daily returns).
"""
from __future__ import annotations
import importlib.util, json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def auth():
    cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("AUTH FAILED"); sys.exit(2)
    return cm.session


def fetch_pnl(session, alpha_id: str, timeout_s: int = 300) -> dict:
    """Return {date: cumulative_pnl}. Polls until the recordset body is ready."""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/recordsets/pnl"
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = session.get(url, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 10)); continue
        if r.status_code != 200:
            raise RuntimeError(f"{alpha_id}: HTTP {r.status_code} {r.text[:150]}")
        if not r.text.strip():
            time.sleep(float(r.headers.get("Retry-After") or 5)); continue
        d = r.json()
        recs = d.get("records") or []
        # records rows: [date, pnl] (schema may add more cols; take first two)
        return {row[0]: row[1] for row in recs}
    raise RuntimeError(f"{alpha_id}: recordset not ready after {timeout_s}s")


def daily_returns(pnl: dict) -> dict:
    dates = sorted(pnl)
    out = {}
    for a, b in zip(dates, dates[1:]):
        va, vb = pnl[a], pnl[b]
        if va is None or vb is None: continue
        out[b] = vb - va
    return out


def corr(x: dict, y: dict) -> float:
    common = sorted(set(x) & set(y))
    if len(common) < 30: return float("nan")
    import math
    xs = [x[d] for d in common]; ys = [y[d] for d in common]
    mx = sum(xs)/len(xs); my = sum(ys)/len(ys)
    cov = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
    vx = sum((a-mx)**2 for a in xs); vy = sum((b-my)**2 for b in ys)
    if vx <= 0 or vy <= 0: return float("nan")
    return cov / math.sqrt(vx*vy)


def main():
    ids = sys.argv[1:]
    if len(ids) < 2:
        print("usage: wq_corr.py ID1 ID2 [...]"); sys.exit(1)
    s = auth()
    rets = {}
    for aid in ids:
        rets[aid] = daily_returns(fetch_pnl(s, aid))
        print(f"fetched {aid}: {len(rets[aid])} daily returns", flush=True)
    print("\ncorrelation matrix (daily pnl):")
    print(" " * 10 + "".join(f"{i:>10}" for i in ids))
    for a in ids:
        row = "".join(f"{corr(rets[a], rets[b]):10.3f}" for b in ids)
        print(f"{a:>10}{row}")


if __name__ == "__main__":
    main()
