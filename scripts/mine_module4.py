"""Module-4: amplify the IV-momentum signal from module-3.

Module-3 found rank(ts_delta(implied_volatility_call_30, 5)) at
TOP1000/SUBINDUSTRY/decay=64 had SH=1.10 FIT=0.63 - close but fitness
short. Try: extra smoothing wrapper, longer IV horizons, and ts_zscore
mean-reversion variants. Push decay up to 128.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("mine4")
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
    # Smoothed IV delta - extra ts_decay/ts_mean wrappers
    "rank(ts_decay_linear(ts_delta(implied_volatility_call_30, 5), 20))",
    "rank(ts_mean(ts_delta(implied_volatility_call_30, 5), 10))",
    # Longer delta horizon
    "rank(ts_delta(implied_volatility_call_30, 20))",
    "rank(ts_delta(implied_volatility_call_60, 10))",
    # IV surprise (vs long mean) - bigger move = more signal
    "rank(implied_volatility_call_30 - ts_mean(implied_volatility_call_30, 60))",
    # Mean-reversion on IV z-score (high IV → buy)
    "-rank(ts_zscore(implied_volatility_call_30, 30))",
    # Smoothed IV surprise with extra decay
    "rank(ts_decay_linear(implied_volatility_call_30 - ts_mean(implied_volatility_call_30, 30), 20))",
    # IV-skew change (re-test with smoothing)
    "rank(ts_decay_linear(ts_delta(implied_volatility_mean_skew_30, 5), 20))",
]

# Heavier decay; SUBINDUSTRY won module-3
SETTINGS_VARIANTS = [
    {"universe": "TOP1000", "neutralization": "SUBINDUSTRY", "truncation": 0.08, "decay": 64},
    {"universe": "TOP1000", "neutralization": "SUBINDUSTRY", "truncation": 0.08, "decay": 128},
    {"universe": "TOP500",  "neutralization": "SUBINDUSTRY", "truncation": 0.08, "decay": 64},
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
    ap.add_argument("--out", default="MINE_MOD4_RESULTS.json")
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
                         f"FIT={isb.get('fitness')} {s['universe']} {s['neutralization']} "
                         f"dec={s['decay']} | {badge} | {e[:60]}")
                res["checks_pass_all"] = ok_all; res["checks_failed_summary"] = why
            else:
                log.info(f"[{i:3d}] ERR {res.get('error','')[:120]} | {s.get('universe')} | {e[:60]}")
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
