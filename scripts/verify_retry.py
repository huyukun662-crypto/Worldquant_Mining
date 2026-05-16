"""Retry verify for alpha_ids that returned empty body in initial pass.

Slower polling (10s/12s gaps), more retries, longer between alphas.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("retry")
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


def check_alpha(session, alpha_id: str) -> dict:
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/check"
    for attempt in range(8):
        r = session.get(url, timeout=30)
        if r.status_code == 429:
            time.sleep(30)
            continue
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code}
        if not r.text.strip():
            time.sleep(10 + attempt * 3)
            continue
        try:
            return {"ok": True, "data": r.json()}
        except Exception as e:
            return {"ok": False, "body": str(e)}
    return {"ok": False, "body": "empty after 8 retries"}


def main():
    aids_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/err_aids.txt"
    aids = [l.strip() for l in open(aids_file) if l.strip()]
    cm = authenticate()
    log.info(f"auth as {cm.credentials.username}; retrying {len(aids)} alphas")
    out = []
    for i, aid in enumerate(aids, 1):
        log.info(f"--- [{i}/{len(aids)}] {aid}")
        res = check_alpha(cm.session, aid)
        if not res.get("ok"):
            log.info(f"   STILL-ERR {res.get('body') or res.get('status')}")
            out.append({"aid": aid, "ok": False, "err": res})
            time.sleep(3)
            continue
        is_checks = (res["data"].get("is") or {}).get("checks") or []
        fails = []
        for c in is_checks:
            if c.get("result") not in ("PASS", "PENDING", None):
                tag = c.get("name", "?")
                if c.get("value") is not None:
                    tag += f"({c['value']})"
                fails.append(tag)
        status = "PASS" if not fails else "FAIL"
        log.info(f"   {status}  {fails}")
        out.append({"aid": aid, "ok": True, "fails": fails})
        time.sleep(3)

    (REPO / "WQ_SUBMISSION_RETRY.json").write_text(json.dumps(out, indent=2))
    print()
    print("=" * 60)
    pass_aids = [r['aid'] for r in out if r.get('ok') and not r.get('fails')]
    fail_aids = [r for r in out if r.get('ok') and r.get('fails')]
    err_aids = [r for r in out if not r.get('ok')]
    print(f"PASS: {len(pass_aids)}  FAIL: {len(fail_aids)}  ERR: {len(err_aids)}")
    print()
    print("PASS aids:")
    for aid in pass_aids: print(f"  {aid}")
    print()
    print("FAIL breakdown:")
    from collections import Counter
    c = Counter()
    for r in fail_aids:
        c[tuple(sorted(r['fails']))] += 1
    for k, n in c.most_common():
        print(f"  {n}x  {list(k)}")


if __name__ == "__main__":
    main()
