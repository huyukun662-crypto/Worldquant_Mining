"""Verify a fetched data-fields cache covers the documented WQ Brain catalog.

Compares the per-category field counts in
`constants/data_fields_cache_USA_1_TOP3000.json` (or the upstream snapshot
we imported) to the expected counts in `expected_field_counts_USA.json`.

Usage:
    python -m worldquant_mining.verify_completeness [path-to-cache.json]
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from typing import Dict


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = os.path.join(REPO_ROOT, "constants", "expected_field_counts_USA.json")
DEFAULT_CACHE = os.path.join(REPO_ROOT, "constants", "upstream_data_fields_USA_TOP3000.json")


def _category_id(field: Dict) -> str:
    cat = field.get("category")
    if isinstance(cat, dict):
        return cat.get("id") or cat.get("name") or "unknown"
    return cat or "unknown"


def _dataset_id(field: Dict) -> str:
    ds = field.get("dataset")
    if isinstance(ds, dict):
        return ds.get("id") or ds.get("name") or "unknown"
    return ds or "unknown"


def verify(cache_path: str = DEFAULT_CACHE,
           expected_path: str = EXPECTED) -> int:
    with open(expected_path) as f:
        spec = json.load(f)
    expected = spec["categories"]

    if not os.path.exists(cache_path):
        print(f"ERROR: cache not found: {cache_path}")
        return 2
    with open(cache_path) as f:
        fields = json.load(f)
    if not isinstance(fields, list):
        print(f"ERROR: cache is not a list of fields")
        return 2

    cat_counts = Counter(_category_id(f) for f in fields)
    cat_datasets: Dict[str, set] = {}
    for f in fields:
        cat_datasets.setdefault(_category_id(f), set()).add(_dataset_id(f))

    total_expected = sum(v["fields"] for v in expected.values())
    total_actual = len(fields)

    print(f"Cache: {cache_path}")
    print(f"Total fields:    expected {total_expected:>5}   actual {total_actual:>5}   "
          f"({total_actual / max(total_expected, 1) * 100:5.1f}%)")
    print()
    print(f"{'category':<14} {'exp_ds':>6} {'act_ds':>6} {'exp_fld':>8} {'act_fld':>8} {'pct':>6} status")

    incomplete = 0
    for cat, info in expected.items():
        exp_ds, exp_fld = info["datasets"], info["fields"]
        act_ds = len(cat_datasets.get(cat, set()))
        act_fld = cat_counts.get(cat, 0)
        pct = act_fld / max(exp_fld, 1) * 100
        status = "OK" if act_fld >= exp_fld else "INCOMPLETE"
        if status == "INCOMPLETE":
            incomplete += 1
        print(f"{cat:<14} {exp_ds:>6} {act_ds:>6} {exp_fld:>8} {act_fld:>8} {pct:5.1f}% {status}")

    print()
    if incomplete:
        print(f"{incomplete} category(s) incomplete. The data-fields fetch did not capture "
              f"the full WQ Brain catalog. If using upstream's fetcher, ensure the relaxed "
              f"limits in vendor/worldquant-miner/data_fetcher/data_field_fetcher.py are in "
              f"effect (offset-based pagination, no max_pages cap).")
        return 1
    print("All categories complete.")
    return 0


if __name__ == "__main__":
    cache = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CACHE
    sys.exit(verify(cache_path=cache))
