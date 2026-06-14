"""One-shot: submit a single confirmed alpha to WQ Brain and poll the
submission checks to completion. Submit Alpha endpoint (NOT /simulations).

Usage: python scripts/submit_one.py <ALPHA_ID>
"""
from __future__ import annotations
import importlib.util, json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _req(method, s, url, **kw):
    kw.setdefault("timeout", 30)
    for a in range(5):
        try:
            return s.request(method, url, **kw)
        except Exception as e:
            print(f"  net-retry {a+1}/5: {str(e)[:60]}", flush=True); time.sleep(2 ** a)
    return None


def main():
    aid = sys.argv[1]
    cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("auth failed"); return 2
    s = cm.session
    print(f"authenticated as {cm.credentials.username}; submitting {aid}", flush=True)

    url = f"https://api.worldquantbrain.com/alphas/{aid}/submit"
    # POST to initiate submission
    r = None
    for attempt in range(8):
        r = _req("POST", s, url)
        if r is None:
            time.sleep(10); continue
        print(f"POST /submit -> {r.status_code}; body={r.text[:200]!r}", flush=True)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            print(f"  429 (concurrent submit limit?); sleep {wait:.0f}s", flush=True)
            time.sleep(wait); continue
        break
    if r is None:
        print("RESULT: network failure on POST"); return 1
    loc = r.headers.get("Location")
    print(f"Location header: {loc}", flush=True)

    # Poll: prefer Location (submit progress); fall back to GET /submit
    poll_url = loc if loc else url
    t0 = time.time()
    last = ""
    while time.time() - t0 < 1200:  # up to 20 min
        time.sleep(6)
        rp = _req("GET", s, poll_url)
        if rp is None:
            continue
        ra = rp.headers.get("Retry-After")
        if rp.status_code == 429:
            time.sleep(20); continue
        if rp.status_code not in (200, 201):
            if rp.status_code != 404:
                print(f"  poll {rp.status_code}: {rp.text[:150]}", flush=True)
            # if polling /submit and it 404s, switch to alpha doc
            poll_url = f"https://api.worldquantbrain.com/alphas/{aid}"
            continue
        if ra:  # still computing
            continue
        try:
            d = rp.json()
        except Exception:
            continue
        # submit-progress doc has 'status'; checks may be under is.checks
        status = d.get("status", "")
        checks = (d.get("is") or {}).get("checks") if isinstance(d.get("is"), dict) else d.get("checks")
        if status and status != last:
            print(f"  status={status} ({int(time.time()-t0)}s)", flush=True)
            last = status
        if checks:
            summary = {c.get("name"): c.get("result") for c in checks}
            print(f"  checks={json.dumps(summary)}", flush=True)
            # terminal if no PENDING among the gating (non-OS) checks
            pend = [k for k, v in summary.items() if v == "PENDING"]
            if status in ("COMPLETE", "FAIL", "ERROR", "WARNING") or not pend:
                print("POLL-TERMINAL", flush=True)
                break
        if status in ("COMPLETE", "FAIL", "ERROR"):
            break

    # Final read of the alpha document
    fa = _req("GET", s, f"https://api.worldquantbrain.com/alphas/{aid}")
    if fa is not None and fa.status_code == 200:
        a = fa.json()
        print("\n=== FINAL ALPHA STATE ===", flush=True)
        print("status:", a.get("status"), "| grade:", a.get("grade"), flush=True)
        print("dateSubmitted:", a.get("dateSubmitted"), flush=True)
        isb = a.get("is") or {}
        print("IS checks:", json.dumps({c.get("name"): c.get("result") for c in isb.get("checks", [])}), flush=True)
        osb = a.get("os")
        if osb:
            print("OS checks:", json.dumps({c.get("name"): c.get("result") for c in (osb.get("checks") or [])}), flush=True)
        json.dump(a, open(REPO / f"SUBMIT_RESULT_{aid}.json", "w"), indent=2)
        print(f"wrote SUBMIT_RESULT_{aid}.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
