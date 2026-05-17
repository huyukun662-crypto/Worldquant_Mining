"""One-shot D0 capability probe.

Submits a single trivial expression (`rank(close)`) to WQ Brain with
`delay=0`. Used to verify whether the account has Research Consultant
(D0) access before launching the D0 mining loop.

Exit codes:
    0 = D0 access confirmed (POST /simulations returned 201, sim completed)
    1 = D0 still gated (HTTP 400 with "Delay 0 is not available")
    2 = other failure (auth, network, unexpected status)
"""
from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("probe-d0")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")

    body = {
        "type": "REGULAR",
        "regular": "rank(close)",
        "settings": {
            "instrumentType": "EQUITY",
            "region":         "USA",
            "universe":       "TOP1000",
            "delay":          0,
            "decay":          0,
            "truncation":     0.08,
            "neutralization": "INDUSTRY",
            "pasteurization": "ON",
            "unitHandling":   "VERIFY",
            "nanHandling":    "OFF",
            "language":       "FASTEXPR",
            "visualization":  False,
            "maxTrade":       "OFF",
            "testPeriod":     "P0Y0M",
        },
    }
    log.info("POST /simulations with delay=0, universe=TOP1000, expr=rank(close)")
    r = cm.session.post("https://api.worldquantbrain.com/simulations",
                        json=body, timeout=30)
    log.info(f"   -> HTTP {r.status_code}")
    body_text = r.text[:600] if r.text else ""
    if r.status_code == 201:
        loc = r.headers.get("Location", "")
        print("D0 OK: HTTP 201, Location=" + loc)
        return 0
    if r.status_code == 400 and "Delay 0 is not available" in body_text:
        print("D0 GATED: HTTP 400 'Delay 0 is not available'")
        print(f"  body: {body_text}")
        return 1
    print(f"D0 UNKNOWN: HTTP {r.status_code}")
    print(f"  body: {body_text}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
