"""Module-7: extend the winning recipe to more MATRIX fields, test delay=0.

The proven recipe is:
    zscore(ts_backfill(ts_delta(<MATRIX field>, N), 250))
    settings: TOP1000 / SUBINDUSTRY / trunc=0.01 / decay=128 / pasteurization=ON

Apply this template to alternative MATRIX time-series fields
(put-IV, IV-skew, HV, news sentiment, fundamental equity) so we
discover signals structurally independent of the Option-call-IV winner.
Also probe delay=0 on the proven winner.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("mine7")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

FIXED_BASE = {
    "instrumentType": "EQUITY", "region": "USA",
    "language": "FASTEXPR",
    "unitHandling": "VERIFY",
    "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    "pasteurization": "ON",
}

# (expression, settings)
JOBS = [
    # === proven recipe on alternative MATRIX fields ===
    # put IV 60 (alternative to call - might have lower self-corr to mod-6 winner)
    ("zscore(ts_backfill(ts_delta(implied_volatility_put_60, 10), 250))",
     {"universe":"TOP1000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"OFF"}),
    # call IV 30 (shorter expiry)
    ("zscore(ts_backfill(ts_delta(implied_volatility_call_30, 10), 250))",
     {"universe":"TOP1000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"OFF"}),
    # IV skew 60
    ("zscore(ts_backfill(ts_delta(implied_volatility_mean_skew_60, 10), 250))",
     {"universe":"TOP1000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"OFF"}),
    # historical vol 60
    ("zscore(ts_backfill(ts_delta(historical_volatility_60, 10), 250))",
     {"universe":"TOP1000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"OFF"}),
    # news composite sentiment momentum
    ("zscore(ts_backfill(ts_delta(mean_composite_sentiment_score, 5), 250))",
     {"universe":"TOP1000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":64,"nanHandling":"OFF"}),
    # event sentiment
    ("zscore(ts_backfill(ts_delta(mean_event_sentiment_score, 10), 250))",
     {"universe":"TOP1000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"OFF"}),
    # fundamental equity change (buybacks/issuance)
    ("zscore(ts_backfill(ts_delta(equity, 60), 250))",
     {"universe":"TOP1000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":64,"nanHandling":"OFF"}),
    # === delay=0 variants of the proven winner ===
    ("zscore(ts_backfill(ts_delta(implied_volatility_call_60, 10), 250))",
     {"universe":"TOP1000","delay":0,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":128,"nanHandling":"OFF"}),
    # delay=0 on PV reversal (mod-1 winner)
    ("-ts_rank(returns, 5)",
     {"universe":"TOP1000","delay":0,"neutralization":"INDUSTRY","truncation":0.08,"decay":32,"nanHandling":"OFF"}),
    # === news_indx_perf with backfill ===
    ("zscore(ts_backfill(ts_delta(news_indx_perf, 10), 250))",
     {"universe":"TOP1000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"decay":64,"nanHandling":"OFF"}),
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
    ap.add_argument("--out", default="MINE_MOD7_RESULTS.json")
    args = ap.parse_args()
    cm = _load_cm(); log.info(f"auth ok as {cm.credentials.username}")
    log.info(f"will submit {len(JOBS)} combos conc={args.concurrency}")
    results = []; out_path = REPO / args.out
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(submit_one, cm.session, e, s): (i, e, s)
                for i, (e, s) in enumerate(JOBS)}
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
                         f"FIT={isb.get('fitness')} d={s['delay']} "
                         f"trunc={s['truncation']} dec={s['decay']} | {badge} | {e[:70]}")
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
        print(f"  SH={isb.get('sharpe')} FIT={isb.get('fitness')} TO={isb.get('turnover')} "
              f"d={s['delay']} trunc={s['truncation']} dec={s['decay']} | {r['alpha_id']} | {r['expr']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
