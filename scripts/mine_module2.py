"""Module-2 miner: switch off PV/reversal, mine Option & News fields.

Per user feedback "this structure doesn't work, switch module": the PV
reversal family gave 6 PASSing alphas but they're all the same idea.
This batch uses the Option (value score 6) and News (sentiment MATRIX)
categories - structurally orthogonal to PV reversal.
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("mine2")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

FIXED = {
    "instrumentType": "EQUITY", "region": "USA",
    "delay": 1, "language": "FASTEXPR",
    "unitHandling": "VERIFY", "nanHandling": "OFF",
    "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    "pasteurization": "ON",
}

# Option-implied & news sentiment candidates. All MATRIX fields, scalar-per-day.
CANDIDATES = [
    # ---- OPTION: IV skew / risk-premium / mean-reversion ----
    # Put-call IV spread (crash fear premium - higher fear -> short)
    "-rank(implied_volatility_put_30 - implied_volatility_call_30)",
    # Vol-risk-premium: realized vs implied
    "rank(historical_volatility_30 - implied_volatility_call_30)",
    # IV mean-reversion (high IV stocks under-perform)
    "-rank(ts_delta(implied_volatility_call_30, 5))",
    # IV term-structure (short-end vs long-end)
    "rank(implied_volatility_call_30 / (implied_volatility_call_90 + 0.001))",
    # IV skew change
    "-rank(ts_delta(implied_volatility_mean_skew_30, 5))",
    # Forward premium (synthetic forward vs spot)
    "rank((forward_price_30 - close) / (close + 0.001))",
    # ---- NEWS: sentiment + impact ----
    # Daily composite sentiment, smoothed
    "rank(ts_mean(mean_composite_sentiment_score, 5))",
    # Earnings-evaluation sentiment
    "rank(ts_mean(mean_earnings_evaluation_sentiment, 5))",
    # Event sentiment with news novelty weighting
    "rank(ts_mean(mean_event_sentiment_score, 10))",
    # News impact projection
    "rank(ts_mean(mean_news_impact_projection, 5))",
    # Sentiment reversion (short-term contrarian on news)
    "-rank(ts_delta(mean_composite_sentiment_score, 3))",
    # Stock vs SPY news perf (alpha-from-news)
    "rank(ts_mean(news_indx_perf, 5))",
]

SETTINGS_VARIANTS = [
    {"universe": "TOP1000", "neutralization": "INDUSTRY",    "truncation": 0.08, "decay": 32},
    {"universe": "TOP1000", "neutralization": "SUBINDUSTRY", "truncation": 0.05, "decay": 64},
    {"universe": "TOP500",  "neutralization": "INDUSTRY",    "truncation": 0.10, "decay": 16},
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
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
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
                return {"ok": False, "expr": expr, "settings": full,
                        "alpha_id": aid, "error": f"GET alpha {ra.status_code}"}
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
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--out", default="MINE_MOD2_RESULTS.json")
    args = ap.parse_args()

    cm = _load_cm(); log.info(f"auth ok as {cm.credentials.username}")
    jobs = [(e, s) for e in CANDIDATES for s in SETTINGS_VARIANTS]
    if args.max: jobs = jobs[:args.max]
    log.info(f"will submit {len(jobs)} (expr, settings) combinations conc={args.concurrency}")

    results = []
    out_path = REPO / args.out
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(submit_one, cm.session, e, s): (i, e, s)
                for i, (e, s) in enumerate(jobs)}
        for fut in as_completed(futs):
            i, e, s = futs[fut]
            try: res = fut.result()
            except Exception as ex_:
                res = {"ok": False, "expr": e, "settings": s, "error": f"exc: {ex_}"}
            tag = "OK " if res.get("ok") else "ERR"
            if res.get("ok"):
                isb = (res["alpha"].get("is") or {})
                sh = isb.get("sharpe"); to = isb.get("turnover"); fit = isb.get("fitness")
                ok_all, why = passes_all_checks(res["alpha"])
                badge = "✅PASS" if ok_all else f"❌{why[:60]}"
                log.info(f"[{i:3d}] {tag} SH={sh} TO={to} FIT={fit} "
                         f"univ={s['universe']} neut={s['neutralization']} "
                         f"dec={s['decay']} | {badge} | {e[:60]}")
                res["checks_pass_all"] = ok_all
                res["checks_failed_summary"] = why
            else:
                log.info(f"[{i:3d}] {tag} {res.get('error','')[:120]} | univ={s.get('universe')} | {e[:60]}")
            results.append(res)
            with open(out_path, "w") as f:
                json.dump(results, f, indent=2, default=str)

    survivors = [r for r in results if r.get("ok") and r.get("checks_pass_all")]
    survivors.sort(key=lambda r: (r["alpha"].get("is") or {}).get("sharpe", 0), reverse=True)
    print(f"\nPASS-ALL: {len(survivors)} / {len(results)}")
    for r in survivors[:15]:
        isb = r["alpha"].get("is") or {}; s = r["settings"]
        print(f"  SH={isb.get('sharpe')} TO={isb.get('turnover')} FIT={isb.get('fitness')} "
              f"univ={s['universe']} neut={s['neutralization']} dec={s['decay']} "
              f"| {r['alpha_id']} | {r['expr']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
