"""Module-6: crack CONCENTRATED_WEIGHT on the IV60-delta-10 signal.

Every module-5 variant with SH>1.25 FIT>1.0 failed CONCENTRATED because
option data is sparse - only ~30-40% of TOP1000 stocks have active option
markets, so the alpha concentrates in those names.

Three approaches:
1. nanHandling=ON - WQ fills NaN with 0 (broadens support).
2. Long ts_backfill (250d) - propagate last known IV-delta forward.
3. Hybrid: IV signal + tiny PV baseline to spread weight across all names.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("mine6")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# Same fixed except nanHandling can be overridden per variant
FIXED_BASE = {
    "instrumentType": "EQUITY", "region": "USA",
    "delay": 1, "language": "FASTEXPR",
    "unitHandling": "VERIFY",
    "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    "pasteurization": "ON",
}

CANDIDATES_AND_SETTINGS = [
    # 1) the SH=1.42 / FIT=1.31 winner with nanHandling=ON to spread
    ("zscore(ts_delta(implied_volatility_call_60, 10))",
     {"universe":"TOP1000","neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"ON"}),
    # 2) same with extra-long backfill (250 trading days)
    ("zscore(ts_backfill(ts_delta(implied_volatility_call_60, 10), 250))",
     {"universe":"TOP1000","neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"OFF"}),
    # 3) backfill + nanHandling combined
    ("zscore(ts_backfill(ts_delta(implied_volatility_call_60, 10), 250))",
     {"universe":"TOP1000","neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"ON"}),
    # 4) rank backfilled
    ("rank(ts_backfill(ts_delta(implied_volatility_call_60, 10), 250))",
     {"universe":"TOP1000","neutralization":"SUBINDUSTRY","truncation":0.05,"decay":128,"nanHandling":"ON"}),
    # 5) scale backfilled
    ("scale(ts_backfill(ts_delta(implied_volatility_call_60, 10), 250))",
     {"universe":"TOP1000","neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"ON"}),
    # 6) HYBRID: IV signal + tiny PV reversal baseline to broaden support
    ("zscore(ts_delta(implied_volatility_call_60, 10)) + 0.2 * zscore(-ts_rank(returns, 10))",
     {"universe":"TOP1000","neutralization":"SUBINDUSTRY","truncation":0.01,"decay":64,"nanHandling":"ON"}),
    # 7) hybrid with smaller PV weight
    ("zscore(ts_delta(implied_volatility_call_60, 10)) + 0.1 * zscore(-ts_rank(returns, 10))",
     {"universe":"TOP1000","neutralization":"SUBINDUSTRY","truncation":0.01,"decay":64,"nanHandling":"ON"}),
    # 8) hybrid: backfilled IV + PV
    ("zscore(ts_backfill(ts_delta(implied_volatility_call_60, 10), 250)) + 0.3 * zscore(-ts_rank(returns, 10))",
     {"universe":"TOP1000","neutralization":"SUBINDUSTRY","truncation":0.05,"decay":64,"nanHandling":"ON"}),
]

POLL_TIMEOUT_S = 700
POLL_INTERVAL_S = 6


def _load_cm():
    spec = importlib.util.spec_from_file_location(
        "cm", VENDOR / "core" / "credential_manager.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    cm = m.CredentialManager(base_path=str(REPO))
    assert cm.authenticate(auto_load=True, auto_prompt=False), "auth failed"
    return cm


def submit_one(session, expr, settings):
    full = dict(FIXED_BASE); full.update(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expr}
    for _ in range(5):
        r = session.post("https://api.worldquantbrain.com/simulations", json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429; sleep {wait:.0f}s"); time.sleep(wait); continue
        break
    if r.status_code != 201:
        return {"ok": False, "expr": expr, "settings": full,
                "error": f"POST {r.status_code}: {r.text[:300]}"}
    prog = r.headers.get("Location")
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(prog, timeout=30)
        if rp.status_code == 429: time.sleep(30); continue
        if rp.status_code != 200: continue
        d = rp.json(); st = d.get("status", "")
        if st == "COMPLETE":
            aid = d.get("alpha")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
            if ra.status_code != 200:
                return {"ok": False, "expr": expr, "settings": full, "alpha_id": aid,
                        "error": f"GET alpha {ra.status_code}"}
            return {"ok": True, "expr": expr, "settings": full,
                    "alpha_id": aid, "alpha": ra.json()}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "expr": expr, "settings": full,
                    "error": f"{st}: {d.get('message','')[:200]}"}
    return {"ok": False, "expr": expr, "settings": full, "error": "poll-timeout"}


def passes_all_checks(alpha):
    isb = (alpha or {}).get("is") or {}
    checks = isb.get("checks") or []
    if not checks: return False, "no-checks"
    failed = []
    for c in checks:
        name = c.get("name"); res = c.get("result")
        if res == "PASS": continue
        if name == "SELF_CORRELATION" and res in ("PENDING",): continue
        failed.append(f"{name}={res}({c.get('value')})")
    return len(failed) == 0, "; ".join(failed) if failed else "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--out", default="MINE_MOD6_RESULTS.json")
    args = ap.parse_args()
    cm = _load_cm(); log.info(f"auth ok as {cm.credentials.username}")
    jobs = list(CANDIDATES_AND_SETTINGS)
    log.info(f"will submit {len(jobs)} (expr, settings) combos conc={args.concurrency}")
    results = []; out_path = REPO / args.out
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(submit_one, cm.session, e, s): (i, e, s)
                for i, (e, s) in enumerate(jobs)}
        for fut in as_completed(futs):
            i, e, s = futs[fut]
            try: res = fut.result()
            except Exception as ex_:
                res = {"ok": False, "expr": e, "settings": s, "error": f"exc: {ex_}"}
            if res.get("ok"):
                isb = (res["alpha"].get("is") or {})
                ok_all, why = passes_all_checks(res["alpha"])
                badge = "✅PASS-ALL" if ok_all else f"❌{why[:60]}"
                log.info(f"[{i:3d}] OK SH={isb.get('sharpe')} TO={isb.get('turnover')} "
                         f"FIT={isb.get('fitness')} nan={s.get('nanHandling')} "
                         f"trunc={s['truncation']} | {badge} | {e[:80]}")
                res["checks_pass_all"] = ok_all; res["checks_failed_summary"] = why
            else:
                log.info(f"[{i:3d}] ERR {res.get('error','')[:120]} | {e[:60]}")
            results.append(res)
            with open(out_path, "w") as f: json.dump(results, f, indent=2, default=str)
    survivors = [r for r in results if r.get("ok") and r.get("checks_pass_all")]
    survivors.sort(key=lambda r: (r["alpha"].get("is") or {}).get("sharpe", 0), reverse=True)
    print(f"\nPASS-ALL: {len(survivors)} / {len(results)}")
    for r in survivors:
        isb = r["alpha"].get("is") or {}; s = r["settings"]
        print(f"  SH={isb.get('sharpe')} TO={isb.get('turnover')} FIT={isb.get('fitness')} "
              f"nan={s.get('nanHandling')} trunc={s['truncation']} | {r['alpha_id']} | {r['expr']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
