"""D0 access probe.

Submits ONE simulation with delay=0 to WQ Brain. Prints D0_OK on
successful COMPLETE; D0_BLOCKED on HTTP 400 "Delay 0 is not available".
This is the gate before any D0 mining work.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("d0-probe")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

D0_TEST_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "universe":       "TOP3000",
    "delay":          0,
    "decay":          4,
    "neutralization": "INDUSTRY",
    "truncation":     0.08,
    "pasteurization": "ON",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "language":       "FASTEXPR",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
}

EXPRESSION = "rank(close - open)"


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
        print("D0_BLOCKED reason=auth")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")

    body = {"type": "REGULAR", "settings": D0_TEST_SETTINGS, "regular": EXPRESSION}
    log.info(f"POST /simulations delay=0 expr={EXPRESSION!r}")
    r = cm.session.post("https://api.worldquantbrain.com/simulations",
                        json=body, timeout=30)
    log.info(f"   status={r.status_code} body={r.text[:300]}")

    if r.status_code == 400 and "Delay 0" in r.text:
        print("D0_BLOCKED reason=HTTP400_delay0_not_available")
        return 1
    if r.status_code != 201:
        print(f"D0_BLOCKED reason=HTTP{r.status_code}: {r.text[:200]}")
        return 1

    progress_url = r.headers.get("Location")
    if not progress_url:
        print("D0_BLOCKED reason=no_location_header")
        return 1
    log.info(f"   submitted, polling {progress_url}")

    t0 = time.time()
    last = ""
    while time.time() - t0 < 600:
        time.sleep(5)
        rp = cm.session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st != last:
            log.info(f"   status={st} ({int(time.time()-t0)}s)")
            last = st
        if st == "COMPLETE":
            alpha_id = data.get("alpha")
            log.info(f"   COMPLETE alpha_id={alpha_id}")
            print(f"D0_OK alpha_id={alpha_id}")
            return 0
        if st in ("ERROR", "FAILED", "WARNING"):
            print(f"D0_BLOCKED reason=sim_{st}: {data.get('message','')[:200]}")
            return 1
    print("D0_BLOCKED reason=poll_timeout")
    return 1


if __name__ == "__main__":
    sys.exit(main())
