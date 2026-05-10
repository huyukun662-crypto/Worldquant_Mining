"""Authenticate against WorldQuant Brain and fetch ALL data fields.

Loads `credential.txt` (gitignored) -> authenticates -> calls the relaxed
DataFieldFetcher -> saves the result to
`constants/data_fields_cache_<REGION>_<DELAY>_<UNIVERSE>.json` -> runs
the completeness verifier.

Usage:
    python scripts/fetch_data_fields.py [REGION] [UNIVERSE] [DELAY]
    python scripts/fetch_data_fields.py USA TOP3000 1
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch")

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR = REPO_ROOT / "vendor" / "worldquant-miner"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    region = sys.argv[1] if len(sys.argv) > 1 else "USA"
    universe = sys.argv[2] if len(sys.argv) > 2 else "TOP3000"
    delay = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    df_mod = _load(VENDOR / "data_fetcher" / "data_field_fetcher.py", "df")

    cm = cm_mod.CredentialManager(base_path=str(REPO_ROOT))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")

    cache_dir = REPO_ROOT / "constants"
    cache_dir.mkdir(exist_ok=True)
    fetcher = df_mod.DataFieldFetcher(session=cm.session, cache_dir=str(cache_dir))

    log.info(f"fetching {region} delay={delay} universe={universe} ...")
    fields = fetcher.fetch_data_fields(region=region, delay=delay, universe=universe,
                                        force_refresh=True)

    out = cache_dir / f"data_fields_cache_{region}_{delay}_{universe}.json"
    with open(out, "w") as f:
        json.dump(fields, f)
    log.info(f"saved {len(fields)} fields -> {out}")

    log.info("running completeness verifier...")
    verify_mod = _load(REPO_ROOT / "worldquant_mining" / "verify_completeness.py",
                        "verify")
    rc = verify_mod.verify(cache_path=str(out))
    return rc


if __name__ == "__main__":
    sys.exit(main())
