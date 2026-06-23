"""Module-3 miner: sign-flipped Option signals + Fundamental value + crosses.

Read from module-2 failure: negative Sharpe means the signal is real,
just wrong sign. ts_delta(implied_volatility_call_30, 5) had SH=-1.1
unflipped → flip and re-test.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("mine3")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

FIXED = {
    "instrumentType": "EQUITY", "region": "USA",
    "delay": 1, "language": "FASTEXPR",
    "unitHandling": "VERIFY", "nanHandling": "OFF",
    "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    "pasteurization": "ON",
}

CANDIDATES = [
    # Option signal-flipped: IV-up after price drop = expect rebound (momentum on IV change)
    "rank(ts_delta(implied_volatility_call_30, 5))",
    "rank(ts_delta(implied_volatility_call_30, 10))",
    # Option: HV exceeds IV (cheap option-implied vol)
    "-rank(historical_volatility_30 - implied_volatility_call_30)",
    # News indx perf reversal (recent news outperformance fades)
    "-rank(ts_mean(news_indx_perf, 5))",
    # Fundamental: book-to-market (value tilt)
    "rank(equity / cap)",
    # Fundamental: high equity / price (cheap)
    "rank(equity / close)",
    # Cross: PV reversal weighted by value
    "-ts_rank(returns, 5) * rank(equity / cap)",
    # Cross: PV reversal weighted by inverse IV (low-vol reversal stronger)
    "-ts_rank(returns, 5) * (-rank(implied_volatility_call_30))",
]

SETTINGS_VARIANTS = [
    {"universe": "TOP1000", "neutralization": "INDUSTRY",    "truncation": 0.08, "decay": 32},
    {"universe": "TOP1000", "neutralization": "SUBINDUSTRY", "truncation": 0.05, "decay": 64},
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
    full = dict(FIXED); full.update(settings)
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
    ap.add_argument("--out", default="MINE_MOD3_RESULTS.json")
    args = ap.parse_args()
    cm = _load_cm(); log.info(f"auth ok as {cm.credentials.username}")
    jobs = [(e, s) for e in CANDIDATES for s in SETTINGS_VARIANTS]
    log.info(f"will submit {len(jobs)} combos conc={args.concurrency}")
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
                badge = "✅PASS" if ok_all else f"❌{why[:60]}"
                log.info(f"[{i:3d}] OK  SH={isb.get('sharpe')} TO={isb.get('turnover')} "
                         f"FIT={isb.get('fitness')} univ={s['universe']} neut={s['neutralization']} "
                         f"dec={s['decay']} | {badge} | {e[:60]}")
                res["checks_pass_all"] = ok_all; res["checks_failed_summary"] = why
            else:
                log.info(f"[{i:3d}] ERR {res.get('error','')[:120]} | univ={s.get('universe')} | {e[:60]}")
            results.append(res)
            with open(out_path, "w") as f: json.dump(results, f, indent=2, default=str)
    survivors = [r for r in results if r.get("ok") and r.get("checks_pass_all")]
    survivors.sort(key=lambda r: (r["alpha"].get("is") or {}).get("sharpe", 0), reverse=True)
    print(f"\nPASS-ALL: {len(survivors)} / {len(results)}")
    for r in survivors:
        isb = r["alpha"].get("is") or {}; s = r["settings"]
        print(f"  SH={isb.get('sharpe')} TO={isb.get('turnover')} FIT={isb.get('fitness')} "
              f"{s['universe']} {s['neutralization']} dec={s['decay']} | {r['alpha_id']} | {r['expr']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
