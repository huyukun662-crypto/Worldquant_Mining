"""Mine D1 alphas from UNCOMMON fields + UNCOMMON operators on WQ Brain.

Per the user spec for this run:
  - delay = 1 only (D1)
  - 冷门字段 (uncommon fields): option8 (implied/historical/parkinson vol,
    IV skew, put/call IV) + socialmedia12 (sentiment / buzz). NOT plain
    price-volume.
  - 冷门算子 (uncommon operators): ts_regression, ts_av_diff, ts_backfill,
    hump, kth_element, ts_quantile, ts_scale, last_diff_value,
    days_from_last_change, group_rank/group_neutralize, signed_power,
    ts_covariance, ts_step, trade_when, bucket.
  - goal: an alpha that passes WQ Brain's submission gate
    (all IS checks PASS + self-correlation < 0.7). We never call /submit;
    we only simulate + run the self-correlation CHECK.

This is NOT template reuse (no Alpha101 / classical lib) -- every
expression is constructed here from raw uncommon fields.

Usage:
    python scripts/mine_uncommon.py --batch 1 --workers 3
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mine")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

FIXED = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "language": "FASTEXPR",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
    "delay": 1,
    "pasteurization": "ON",
}

SHARPE_FLOOR = 1.25
FITNESS_FLOOR = 1.0
TURNOVER_LO, TURNOVER_HI = 0.01, 0.70


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _req(method, session, url, **kw):
    """Resilient request: retries on network exceptions, returns None on
    persistent failure (caller decides what to do)."""
    kw.setdefault("timeout", 30)
    for attempt in range(4):
        try:
            return session.request(method, url, **kw)
        except Exception as e:  # ConnectionError / ReadTimeout / etc.
            log.info(f"   net-retry {attempt+1}/4 {method} {url[-30:]}: {str(e)[:60]}")
            time.sleep(2 ** attempt)
    return None


def submit_and_poll(session, expr, settings, timeout=600, interval=5):
    body = {"type": "REGULAR",
            "settings": {**FIXED, **settings},
            "regular": expr}
    r = None
    # Be patient on 429: concurrent-sim slots can stay full for minutes when
    # abandoned sims are draining. Wait up to ~10 min for a free slot.
    for _ in range(40):
        r = _req("POST", session, "https://api.worldquantbrain.com/simulations",
                 json=body)
        if r is None:
            time.sleep(10); continue
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 15)); continue
        break
    if r is None:
        return {"ok": False, "expr": expr, "settings": settings,
                "error": "submit-network-failure"}
    if r.status_code != 201:
        return {"ok": False, "expr": expr, "settings": settings,
                "error": f"submit-{r.status_code}:{r.text[:160]}"}
    loc = r.headers.get("Location")
    if not loc:
        return {"ok": False, "expr": expr, "settings": settings,
                "error": "no-location"}
    # WQ returns the progress URL as http://host:443/... -- polling that raw
    # yields HTTP 400 ("plain HTTP sent to HTTPS port") and the sim is never
    # read to COMPLETE, leaving a zombie that clogs the concurrent-sim quota.
    loc = loc.replace("http://", "https://").replace(":443", "")
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(interval)
        rp = _req("GET", session, loc)
        if rp is None:
            continue
        if rp.status_code == 429:
            time.sleep(20); continue
        if rp.status_code != 200:
            continue
        try:
            d = rp.json()
        except Exception:
            continue
        st = d.get("status", "")
        if st == "COMPLETE":
            aid = d.get("alpha")
            ra = _req("GET", session, f"https://api.worldquantbrain.com/alphas/{aid}")
            if ra is None or ra.status_code != 200:
                code = ra.status_code if ra is not None else "net"
                return {"ok": False, "expr": expr, "settings": settings,
                        "error": f"alpha-get-{code}", "alpha_id": aid}
            a = ra.json(); isb = a.get("is") or {}
            checks = isb.get("checks") or []
            cd = {c.get("name"): c.get("result") for c in checks}
            return {"ok": True, "expr": expr, "settings": settings,
                    "alpha_id": aid,
                    "sharpe": isb.get("sharpe"), "fitness": isb.get("fitness"),
                    "turnover": isb.get("turnover"), "returns": isb.get("returns"),
                    "drawdown": isb.get("drawdown"), "margin": isb.get("margin"),
                    "longCount": isb.get("longCount"), "shortCount": isb.get("shortCount"),
                    "checks": cd}
        if st in ("ERROR", "FAILED"):
            return {"ok": False, "expr": expr, "settings": settings,
                    "error": f"sim-{st}:{d.get('message','')[:160]}"}
    return {"ok": False, "expr": expr, "settings": settings, "error": "timeout"}


def is_submittable_is(res):
    """All IS checks PASS (SELF_CORRELATION may be PENDING)."""
    if not res.get("ok"):
        return False
    c = res.get("checks", {})
    hard = ["LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
            "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"]
    return all(c.get(k) == "PASS" for k in hard)


def self_correlation(session, alpha_id, timeout=120):
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self"
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = _req("GET", session, url)
        if r is None:
            time.sleep(3); continue
        ra = r.headers.get("Retry-After")
        if r.status_code == 200 and not ra:
            d = r.json()
            props = [p["name"] for p in d["schema"]["properties"]]
            ci = props.index("correlation")
            recs = d.get("records", [])
            mx = max((row[ci] for row in recs), default=0.0)
            return {"max_corr": mx, "n": len(recs)}
        time.sleep(float(ra) if ra else 2)
    return {"max_corr": None, "n": None, "error": "timeout"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default="UNCOMMON_MINING.json")
    ap.add_argument("--candidates", default="candidates.json",
                    help="JSON list of {expr, settings} to simulate")
    args = ap.parse_args()

    # Auth with retry: the container clock skews intermittently, breaking TLS
    # cert validation ("certificate is not yet valid"); retry past those windows.
    cm = None
    for attempt in range(12):
        cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
            base_path=str(REPO))
        if cm.authenticate(auto_load=True, auto_prompt=False):
            break
        log.info(f"auth retry {attempt+1}/12 (clock skew?)"); time.sleep(10)
    else:
        log.error("auth failed after retries"); return 2
    log.info(f"auth ok as {cm.credentials.username}")
    s = cm.session

    cands = json.load(open(REPO / args.candidates))
    log.info(f"{len(cands)} candidates, {args.workers} workers")

    results = []
    out_path = REPO / args.out
    # resume
    if out_path.exists():
        try:
            results = json.load(open(out_path))
            # Only treat OK results as done; retry prior errors (e.g. timeouts).
            done = {(r["expr"], json.dumps(r["settings"], sort_keys=True))
                    for r in results if r.get("ok")}
            results = [r for r in results if r.get("ok")]
            cands = [c for c in cands
                     if (c["expr"], json.dumps(c["settings"], sort_keys=True)) not in done]
            log.info(f"resume: {len(results)} ok kept, {len(cands)} to (re)run")
        except Exception:
            results = []

    def work(c):
        return submit_and_poll(s, c["expr"], c["settings"])

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, c): c for c in cands}
        for fut in as_completed(futs):
            try:
                res = fut.result()
            except Exception as e:
                c = futs[fut]
                res = {"ok": False, "expr": c["expr"], "settings": c["settings"],
                       "error": f"worker-exc:{str(e)[:80]}"}
            results.append(res)
            json.dump(results, open(out_path, "w"), indent=2)
            if res.get("ok"):
                tag = "SUBMIT-IS" if is_submittable_is(res) else "        "
                log.info(f"[{tag}] SH={res['sharpe']} FIT={res['fitness']} "
                         f"TO={res['turnover']} | {res['expr'][:70]}")
            else:
                log.info(f"[ERR] {res.get('error','')[:60]} | {res['expr'][:60]}")

    # Rank survivors
    surv = [r for r in results if is_submittable_is(r)]
    surv.sort(key=lambda r: (r.get("sharpe") or 0), reverse=True)
    print("\n" + "=" * 100)
    print(f"IS-submittable candidates: {len(surv)} / {sum(1 for r in results if r.get('ok'))} ok")
    for r in surv[:15]:
        st = r["settings"]
        print(f"  SH={r['sharpe']:.2f} FIT={r['fitness']:.2f} TO={r['turnover']:.3f} "
              f"neut={st.get('neutralization')} dec={st.get('decay')} uni={st.get('universe')} "
              f"id={r['alpha_id']}\n     {r['expr']}")
    print("=" * 100)

    # Self-correlation on top survivors
    for r in surv[:5]:
        sc = self_correlation(s, r["alpha_id"])
        r["self_corr"] = sc
        verdict = "PASS" if (sc.get("max_corr") is not None and sc["max_corr"] < 0.7) else "?"
        print(f"  self-corr {r['alpha_id']}: max={sc.get('max_corr')} ({verdict})")
    json.dump(results, open(out_path, "w"), indent=2)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
