"""Reusable WorldQuant Brain client for D0 factor mining + submission CHECK.

This does NOT submit alphas (POST /alphas/{id}/submit). It only:
  - runs /simulations (backtest)
  - fetches /alphas/{id} IS metrics + checks
  - runs the pre-submit check via GET /alphas/{id}/check
  - polls GET /alphas/{id}/correlations/self for the async SELF_CORRELATION
"""
from __future__ import annotations
import importlib.util, json, time, logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
API = "https://api.worldquantbrain.com"
log = logging.getLogger("wq")

def _load(p, n):
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def auth():
    cm = _load(VENDOR/"core"/"credential_manager.py", "cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        raise SystemExit("auth failed")
    return cm.session

FIXED = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR",
    "unitHandling":"VERIFY","nanHandling":"OFF","visualization":False,
    "maxTrade":"OFF","testPeriod":"P0Y0M",
}
D0_DEFAULT = {
    "universe":"TOP3000","delay":0,"decay":0,"neutralization":"SUBINDUSTRY",
    "truncation":0.08,"pasteurization":"ON",
}

def simulate(session, expr, settings=None, poll_timeout=420, poll_interval=4):
    s = dict(FIXED); s.update(D0_DEFAULT)
    if settings: s.update(settings)
    body = {"type":"REGULAR","settings":s,"regular":expr}
    for attempt in range(12):
        r = session.post(f"{API}/simulations", json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 0) or min(20 + attempt*15, 90)
            time.sleep(wait); continue
        if r.status_code == 201: break
        return {"ok":False,"expr":expr,"settings":s,"error":f"submit-{r.status_code}:{r.text[:200]}"}
    else:
        return {"ok":False,"expr":expr,"settings":s,"error":"429-exhausted"}
    loc = r.headers.get("Location")
    if not loc:
        return {"ok":False,"expr":expr,"settings":s,"error":"no-location"}
    t0 = time.time()
    while time.time()-t0 < poll_timeout:
        time.sleep(poll_interval)
        rp = session.get(loc, timeout=30)
        if rp.status_code == 429: time.sleep(20); continue
        if rp.status_code != 200: continue
        d = rp.json(); st = d.get("status","")
        if st == "COMPLETE":
            aid = d.get("alpha")
            a = session.get(f"{API}/alphas/{aid}", timeout=30).json()
            isb = a.get("is",{}) or {}
            checks = isb.get("checks",[]) or []
            # CRITICAL: verify the returned alpha really is THIS expression.
            # Under concurrency/load the polled alpha id can be cross-wired;
            # always confirm regular.code matches before trusting metrics.
            code = (a.get("regular",{}) or {}).get("code","")
            code_match = "".join(code.split()) == "".join(expr.split())
            return {"ok":True,"expr":expr,"settings":s,"alpha_id":aid,
                    "code":code,"code_match":code_match,
                    "sharpe":isb.get("sharpe"),"turnover":isb.get("turnover"),
                    "fitness":isb.get("fitness"),"returns":isb.get("returns"),
                    "drawdown":isb.get("drawdown"),"margin":isb.get("margin"),
                    "longCount":isb.get("longCount"),"shortCount":isb.get("shortCount"),
                    "checks":checks}
        if st in ("ERROR","FAILED","WARNING"):
            return {"ok":False,"expr":expr,"settings":s,"alpha_id":d.get("alpha"),
                    "error":f"sim-{st}:{str(d.get('message'))[:200]}"}
    return {"ok":False,"expr":expr,"settings":s,"error":"poll-timeout"}

def simulate_many(session, jobs, max_workers=3):
    """DEPRECATED / UNSAFE. Sharing one requests.Session across threads here
    caused polled alpha ids to cross-wire under load (metrics attributed to the
    wrong expression). Use serial `simulate()` calls or `scripts/measure_serial.py`
    and ALWAYS check `code_match`. Kept only for backward compatibility; it now
    authenticates a FRESH session per job and verifies code_match.
    """
    out = []
    def _run(e, st):
        r = simulate(auth(), e, st)
        if r.get("ok") and not r.get("code_match", True):
            r["ok"] = False; r["error"] = f"code-mismatch (got {r.get('code')!r})"
        return r
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_run, e, st) for e, st in jobs]
        for f in as_completed(futs):
            out.append(f.result())
    return out

def submit_check(session, alpha_id):
    """GET /alphas/{id}/check -> the pre-submit check block."""
    r = session.get(f"{API}/alphas/{alpha_id}/check", timeout=30)
    return r.status_code, (r.json() if r.status_code==200 and r.text else {})

def self_corr(session, alpha_id, poll=20, interval=6):
    """Poll GET /alphas/{id}/correlations/self until it returns data."""
    for _ in range(poll):
        r = session.get(f"{API}/alphas/{alpha_id}/correlations/self", timeout=30)
        if r.status_code == 200 and r.text.strip():
            try: return r.json()
            except Exception: return {"raw": r.text[:500]}
        time.sleep(interval)
    return None
