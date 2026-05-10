"""Multi-slice fetch: union of fields across (delay, universe) pairs.

The WQ Brain UI's per-category totals (e.g. analyst=1374) are taken across
multiple (delay, universe) combinations — they are NOT the count for a
single slice. A (USA, TOP3000, delay=1) fetch caps out at ~5,905 fields
even though the UI shows 7,831 because some fields only appear under
delay=0 or under different universes.

This script fetches a list of (delay, universe) slices, runs the
authenticated fetcher for each, and writes a single unioned cache plus a
verification report.

Default slices: delay in {0, 1} for the standard USA universes.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch-all")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Sweep all USA (universe, delay) pairs documented in
# vendor/worldquant-miner/core/region_config.py. The screenshot's category
# totals are the union across these slices - any single slice will be
# strictly less.
USA_UNIVERSES = ["TOP3000", "TOP1000", "TOP500", "TOP200", "ILLIQUID_MINVOL1M"]
SLICES = [("USA", u, d) for u in USA_UNIVERSES for d in (0, 1)]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    df_mod = _load(VENDOR / "data_fetcher" / "data_field_fetcher.py", "df")

    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")

    cache_dir = REPO / "constants"
    cache_dir.mkdir(exist_ok=True)
    fetcher = df_mod.DataFieldFetcher(session=cm.session, cache_dir=str(cache_dir))

    union: dict[tuple, dict] = {}
    for region, universe, delay in SLICES:
        log.info(f"=== fetching {region} {universe} delay={delay} ===")
        try:
            fields = fetcher.fetch_data_fields(
                region=region, delay=delay, universe=universe, force_refresh=True,
            )
        except Exception as e:
            log.error(f"slice failed: {e}")
            continue
        slice_path = cache_dir / f"data_fields_cache_{region}_{delay}_{universe}.json"
        with open(slice_path, "w") as f:
            json.dump(fields, f)
        log.info(f"slice saved: {slice_path} ({len(fields)} fields)")
        for fld in fields:
            key = (fld.get("id"),
                   fld.get("region"),
                   fld.get("universe"),
                   fld.get("delay"))
            union[key] = fld

    union_fields = list(union.values())
    out_path = cache_dir / f"data_fields_union_USA.json"
    with open(out_path, "w") as f:
        json.dump(union_fields, f)
    log.info(f"union saved: {out_path} ({len(union_fields)} fields)")

    # Per-category breakdown
    by_cat: dict[str, set] = defaultdict(set)
    by_ds: dict[str, int] = defaultdict(int)
    for fld in union_fields:
        cat = fld.get("category", {})
        cat_id = cat.get("id") if isinstance(cat, dict) else cat
        ds = fld.get("dataset", {})
        ds_id = ds.get("id") if isinstance(ds, dict) else ds
        by_cat[cat_id].add(fld["id"])
        by_ds[ds_id] += 1
    log.info("=== union by category (distinct field ids) ===")
    for c, ids in sorted(by_cat.items()):
        log.info(f"  {c:<14} {len(ids):>5} distinct fields")

    # Run the verifier on the unioned cache
    log.info("=== verifier on union ===")
    v = _load(REPO / "worldquant_mining" / "verify_completeness.py", "verify")
    v.verify(cache_path=str(out_path))


if __name__ == "__main__":
    main()
