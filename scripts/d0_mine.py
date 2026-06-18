"""D0 (delay=0) factor miner / submit-check helper for WQ Brain.

Submits expressions at delay=0, polls, fetches IS metrics + submission
checks, and (optionally) runs the self-correlation pre-check so we can
confirm an alpha is *submittable* without actually submitting it.

Usage:
    python scripts/d0_mine.py "expr1" "expr2" ...
    python scripts/d0_mine.py --corr ALPHA_ID    # self-corr only
"""
from __future__ import annotations
import json, sys, time, argparse
import requests

BASE = "https://api.worldquantbrain.com"

D0_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 0,
    "decay": 0,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}


def auth():
    u, p = json.load(open("credential.txt"))
    s = requests.Session()
    r = s.post(f"{BASE}/authentication", auth=(u, p), timeout=30)
    r.raise_for_status()
    return s


def submit(s, expr, settings_override=None, poll_timeout=900):
    settings = dict(D0_SETTINGS)
    if settings_override:
        settings.update(settings_override)
    body = {"type": "REGULAR", "settings": settings, "regular": expr}
    for attempt in range(5):
        r = s.post(f"{BASE}/simulations", json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 20)); continue
        break
    if r.status_code != 201:
        return {"ok": False, "stage": "submit", "code": r.status_code,
                "body": r.text[:400], "expression": expr}
    loc = r.headers.get("Location")
    t0 = time.time()
    while time.time() - t0 < poll_timeout:
        time.sleep(5)
        rp = s.get(loc, timeout=30)
        if rp.status_code == 429:
            time.sleep(20); continue
        if rp.status_code != 200:
            continue
        d = rp.json()
        st = d.get("status", "")
        if st == "COMPLETE":
            aid = d.get("alpha")
            ra = s.get(f"{BASE}/alphas/{aid}", timeout=30)
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            return {"ok": True, "alpha_id": aid, "expression": expr,
                    "sharpe": isb.get("sharpe"), "turnover": isb.get("turnover"),
                    "fitness": isb.get("fitness"), "returns": isb.get("returns"),
                    "drawdown": isb.get("drawdown"), "margin": isb.get("margin"),
                    "longCount": isb.get("longCount"), "shortCount": isb.get("shortCount"),
                    "checks": checks, "settings": settings}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "sim", "status": st,
                    "message": d.get("message", "")[:400], "expression": expr}
    return {"ok": False, "stage": "timeout", "expression": expr}


def self_corr(s, alpha_id, poll_timeout=300):
    """Run self-correlation check. Returns max correlation vs submitted pool."""
    t0 = time.time()
    while time.time() - t0 < poll_timeout:
        r = s.get(f"{BASE}/alphas/{alpha_id}/correlations/self", timeout=30)
        if r.status_code == 429:
            time.sleep(15); continue
        if r.status_code in (200, 201):
            try:
                d = r.json()
            except Exception:
                time.sleep(5); continue
            if not d:
                time.sleep(5); continue
            return d
        time.sleep(5)
    return None


def print_result(r):
    if not r.get("ok"):
        print(f"  ERR [{r.get('stage')}] {r.get('message') or r.get('body') or r.get('status')}")
        return
    print(f"  alpha_id={r['alpha_id']}  SH={r['sharpe']}  TO={r['turnover']}  "
          f"FIT={r['fitness']}  RET={r['returns']}  DD={r['drawdown']}  "
          f"margin={r.get('margin')}  L/S={r.get('longCount')}/{r.get('shortCount')}")
    fails = [c for c in r["checks"] if c.get("result") not in ("PASS", "PENDING")]
    npass = sum(1 for c in r["checks"] if c.get("result") == "PASS")
    print(f"  checks {npass}/{len(r['checks'])} PASS")
    for c in r["checks"]:
        if c.get("result") != "PASS":
            print(f"     {c.get('name')}: {c.get('result')} "
                  f"(value={c.get('value')}, limit={c.get('limit')})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exprs", nargs="*")
    ap.add_argument("--corr", help="alpha_id to run self-correlation on")
    ap.add_argument("--neut", default=None)
    ap.add_argument("--universe", default=None)
    ap.add_argument("--decay", type=int, default=None)
    ap.add_argument("--delay", type=int, default=None)
    args = ap.parse_args()
    s = auth()
    print("authenticated", file=sys.stderr)

    if args.corr:
        d = self_corr(s, args.corr)
        print(json.dumps(d, indent=2)[:2000])
        return

    override = {}
    if args.neut: override["neutralization"] = args.neut
    if args.universe: override["universe"] = args.universe
    if args.decay is not None: override["decay"] = args.decay
    if args.delay is not None: override["delay"] = args.delay

    out = []
    for e in args.exprs:
        print(f"\n=== {e}")
        r = submit(s, e, override or None)
        print_result(r)
        out.append(r)
    json.dump(out, open("D0_RESULTS.json", "w"), indent=2, default=str)


if __name__ == "__main__":
    main()
