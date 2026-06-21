"""Fetch a WQ alpha's IS PnL series and compute pairwise correlation of
daily PnL changes between two alphas. Used to find alphas DECORRELATED
from a reference (the champion), for portfolio diversification."""
import importlib.util
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

def auth():
    spec = importlib.util.spec_from_file_location("cm", VENDOR/"core"/"credential_manager.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    cm = m.CredentialManager(base_path=str(REPO)); cm.authenticate(auto_load=True, auto_prompt=False)
    return cm.session

def pnl_series(session, alpha_id):
    import time
    for _ in range(10):
        r = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}/recordsets/pnl", timeout=30)
        if r.status_code == 200 and r.text.strip():
            d = r.json()
            recs = d.get("records", [])
            if recs:
                # records: [date, pnl]; schema in d['schema']['properties']
                return {row[0]: row[1] for row in recs}
        time.sleep(3)
    return {}

def daily_returns(pnl):
    # pnl is cumulative; daily change
    items = sorted(pnl.items())
    out = {}
    prev = None
    for dt, v in items:
        if prev is not None:
            out[dt] = v - prev
        prev = v
    return out

def corr(a_id, b_id, session=None):
    import math
    session = session or auth()
    pa = daily_returns(pnl_series(session, a_id))
    pb = daily_returns(pnl_series(session, b_id))
    keys = sorted(set(pa) & set(pb))
    if len(keys) < 30: return None, len(keys)
    xa = [pa[k] for k in keys]; xb = [pb[k] for k in keys]
    ma = sum(xa)/len(xa); mb = sum(xb)/len(xb)
    cov = sum((x-ma)*(y-mb) for x,y in zip(xa,xb))
    va = sum((x-ma)**2 for x in xa); vb = sum((y-mb)**2 for y in xb)
    if va*vb == 0: return None, len(keys)
    return cov/math.sqrt(va*vb), len(keys)

if __name__ == "__main__":
    import sys
    s = auth()
    p = pnl_series(s, "QPajYRKg")
    print("champion QPajYRKg pnl points:", len(p))
    if len(sys.argv) > 2:
        c, n = corr(sys.argv[1], sys.argv[2], s)
        print(f"corr({sys.argv[1]},{sys.argv[2]}) = {c} over {n} days")
