"""Verify zero-warn alphas via WQ Brain's /alphas/{id}/check endpoint.

Beyond is.checks, WQ has a full submission-time validation including
SELF_CORRELATION (vs existing alpha pool), PROD_CORRELATION, and others.
This script hits /alphas/{id}/check on each clean alpha and reports which
ones would actually clear the submit gate.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("verify")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def authenticate():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        raise RuntimeError("WQ auth failed")
    return cm


def check_alpha(session, alpha_id: str, max_retries: int = 4) -> dict:
    """GET /alphas/{id}/check.  Sometimes returns empty body if check is
    being computed; retry with backoff."""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/check"
    for attempt in range(max_retries):
        r = session.get(url, timeout=30)
        if r.status_code == 429:
            time.sleep(15)
            continue
        if r.status_code == 401:
            return {"ok": False, "status": 401, "body": "auth-expired"}
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code, "body": r.text[:300]}
        if not r.text.strip():
            time.sleep(5 * (attempt + 1))
            continue
        try:
            return {"ok": True, "data": r.json()}
        except Exception as e:
            return {"ok": False, "status": r.status_code, "body": str(e)}
    return {"ok": False, "status": 200, "body": "empty body after retries"}


def load_zero_warn(top_n: int | None = None) -> list[dict]:
    d = json.loads((REPO / "WQ_QUANTML_RESULTS.json").read_text())
    best = {}
    for r in d:
        if not r.get("ok"): continue
        a = (r.get("alpha") or {}).get("is") or {}
        sh, to, fit = a.get("sharpe"), a.get("turnover"), a.get("fitness")
        if sh is None or to is None or fit is None: continue
        if not (sh > 1.25 and to < 0.25 and fit > 1.0): continue
        fails = [c.get("name") for c in (a.get("checks") or [])
                 if c.get("result") not in ("PASS", "PENDING", None)]
        if fails: continue
        e = r.get("expression", "").strip()
        rec = {
            "sh": sh, "to": to, "fit": fit, "aid": r.get("alpha_id"),
            "expr": e,
        }
        if e not in best or sh > best[e]["sh"]:
            best[e] = rec
    rows = sorted(best.values(), key=lambda x: -x["sh"])
    return rows[:top_n] if top_n else rows


def main():
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    cm = authenticate()
    log.info(f"auth as {cm.credentials.username}")
    rows = load_zero_warn(top_n=top_n)
    log.info(f"checking top {len(rows)} zero-warn alphas")

    out = []
    for i, r in enumerate(rows, 1):
        log.info(f"--- [{i}/{len(rows)}] {r['aid']}  SH {r['sh']:.2f}")
        res = check_alpha(cm.session, r["aid"])
        if not res.get("ok"):
            log.info(f"   ERR status={res.get('status')} body={(res.get('body') or '')[:100]}")
            out.append({**r, "check": res})
            continue
        data = res["data"]
        is_checks = (data.get("is") or {}).get("checks") or []
        fails = []
        for c in is_checks:
            if c.get("result") not in ("PASS", "PENDING", None):
                tag = c.get("name", "?")
                if c.get("value") is not None:
                    tag += f"({c['value']})"
                fails.append(tag)
        if fails:
            log.info(f"   FAIL: {fails}")
        else:
            log.info(f"   PASS  (all checks incl SELF_CORRELATION)")
        out.append({**r, "check": {"ok": True, "fails": fails, "data": data}})
        # WQ rate limit: pause between alphas
        time.sleep(2)

    (REPO / "WQ_SUBMISSION_CHECK.json").write_text(json.dumps(out, indent=2))
    log.info(f"saved to WQ_SUBMISSION_CHECK.json")

    print()
    print("=" * 80)
    cleared = [r for r in out if r["check"].get("ok") and not r["check"].get("fails")]
    print(f"CLEARED submission check: {len(cleared)}/{len(out)}")
    for r in cleared:
        print(f"  {r['aid']}  SH {r['sh']:.2f}  TO {r['to']:.3f}  FIT {r['fit']:.2f}")
    print()
    failed = [r for r in out if r["check"].get("ok") and r["check"].get("fails")]
    print(f"FAILED submission check: {len(failed)}/{len(out)}")
    for r in failed:
        print(f"  {r['aid']}  SH {r['sh']:.2f}  fails={r['check']['fails']}")


if __name__ == "__main__":
    main()
