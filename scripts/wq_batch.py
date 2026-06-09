"""Concurrent batch tester for WQ Brain /simulations (delay-0 focus).

Reads a JSON list of candidates [{"expr": str, "settings": {...overrides}}],
POSTs them with bounded concurrency (account allows ~3 concurrent sims),
polls each to COMPLETE, fetches /alphas/{id}, and prints a compact table of
the submission-relevant check values.

Usage:
    python scripts/wq_batch.py candidates.json [out.json]
"""
from __future__ import annotations
import importlib.util, json, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 0, "decay": 6, "neutralization": "SUBINDUSTRY",
    "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY",
    "nanHandling": "OFF", "language": "FASTEXPR", "visualization": False,
    "maxTrade": "OFF", "testPeriod": "P0Y0M",
}

MAX_CONCURRENT = 2
POLL_TIMEOUT_S = 600


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def auth():
    cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("AUTH FAILED"); sys.exit(2)
    print("authenticated as", cm.credentials.username, flush=True)
    return cm.session


def run_one(session, cand):
    expr = cand["expr"]
    settings = dict(BASE_SETTINGS); settings.update(cand.get("settings", {}))
    body = {"type": "REGULAR", "settings": settings, "regular": expr}
    # POST with 429 backoff
    for _ in range(6):
        r = session.post("https://api.worldquantbrain.com/simulations", json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 15)); continue
        break
    if r.status_code != 201:
        return {"ok": False, "expr": expr, "settings": settings,
                "error": f"submit-{r.status_code}: {r.text[:200]}"}
    loc = r.headers.get("Location")
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(5)
        rp = session.get(loc, timeout=30)
        if rp.status_code == 429: time.sleep(15); continue
        if rp.status_code != 200: continue
        data = rp.json(); st = data.get("status", "")
        if st == "COMPLETE":
            aid = data.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
            ay = ra.json(); isb = ay.get("is") or {}
            checks = {c.get("name"): c for c in (isb.get("checks") or [])}
            return {"ok": True, "expr": expr, "settings": settings, "alpha_id": aid,
                    "sharpe": isb.get("sharpe"), "turnover": isb.get("turnover"),
                    "fitness": isb.get("fitness"), "returns": isb.get("returns"),
                    "drawdown": isb.get("drawdown"), "margin": isb.get("margin"),
                    "longCount": isb.get("longCount"), "shortCount": isb.get("shortCount"),
                    "checks": checks}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "expr": expr, "settings": settings,
                    "error": f"sim-{st}: {data.get('message','')[:200]}"}
    return {"ok": False, "expr": expr, "settings": settings, "error": "timeout"}


def fmt(x):
    return f"{x:7.3f}" if isinstance(x, (int, float)) else "   -   "


def passes_d0(r):
    """All submission checks pass at delay-0 thresholds."""
    if not r.get("ok"): return False
    c = r["checks"]
    def ok(name): return c.get(name, {}).get("result") == "PASS"
    fails = [n for n in ("LOW_SHARPE","LOW_FITNESS","HIGH_TURNOVER","LOW_TURNOVER",
             "CONCENTRATED_WEIGHT","LOW_SUB_UNIVERSE_SHARPE") if not ok(n)]
    return fails


def main():
    cands = json.load(open(sys.argv[1]))
    out_path = sys.argv[2] if len(sys.argv) > 2 else "wq_batch_results.json"
    session = auth()
    results = [None] * len(cands)
    def _flush():
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as ex:
        futs = {ex.submit(run_one, session, c): i for i, c in enumerate(cands)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as e:
                results[i] = {"ok": False, "expr": cands[i]["expr"], "error": str(e)}
            _flush()  # incremental: survive a mid-run kill
            r = results[i]
            if r.get("ok"):
                c = r["checks"]
                sh_lim = c.get("LOW_SHARPE", {}).get("limit")
                fit_lim = c.get("LOW_FITNESS", {}).get("limit")
                fails = passes_d0(r)
                tag = "*** SUBMITTABLE ***" if not fails else f"fails={fails}"
                print(f"[{i:2}] SH={fmt(r['sharpe'])} TO={fmt(r['turnover'])} "
                      f"FIT={fmt(r['fitness'])} RET={fmt(r['returns'])} "
                      f"DD={fmt(r['drawdown'])} | SHlim={sh_lim} FITlim={fit_lim} "
                      f"| {tag} | {r['expr'][:70]}", flush=True)
            else:
                print(f"[{i:2}] ERR {r.get('error','')[:90]} | {r.get('expr','')[:60]}", flush=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print("wrote", out_path, flush=True)
    # summary of submittable
    subs = [r for r in results if r and r.get("ok") and not passes_d0(r)]
    print(f"\n=== {len(subs)} SUBMITTABLE candidates ===")
    for r in subs:
        print(f"  SH={r['sharpe']} TO={r['turnover']} FIT={r['fitness']} | {r['expr']}")


if __name__ == "__main__":
    main()
