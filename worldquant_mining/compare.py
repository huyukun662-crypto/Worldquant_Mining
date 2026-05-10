"""
Diff the upstream worldquant-miner snapshots against the canonical
catalogs and emit a human-readable gap report.

Usage:
    python -m worldquant_mining.compare
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Tuple

from .operators import CANONICAL_OPERATORS, operators_by_category
from .data_fields import (
    PV_STANDARD_FIELDS,
    GROUP_FIELDS,
    DEFAULT_UNIVERSES,
    EXPECTED_CATEGORIES,
    data_fields_by_category,
)
from .factor_templates import ALL_TEMPLATES, ALPHA_101, CLASSICAL_FACTORS


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONST_DIR = os.path.join(REPO_ROOT, "constants")


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

def diff_operators(
    upstream_path: str = os.path.join(CONST_DIR, "upstream_operatorRAW.json"),
) -> Dict:
    with open(upstream_path) as f:
        upstream = json.load(f)
    up_names = {op["name"] for op in upstream}
    canonical_names = {op["name"] for op in CANONICAL_OPERATORS}

    missing = sorted(canonical_names - up_names)
    only_upstream = sorted(up_names - canonical_names)

    canon_by_cat = {c: [o["name"] for o in ops] for c, ops in operators_by_category().items()}
    up_by_cat: Dict[str, List[str]] = {}
    for op in upstream:
        up_by_cat.setdefault(op["category"], []).append(op["name"])

    return {
        "upstream_count": len(up_names),
        "canonical_count": len(canonical_names),
        "added_to_canonical": missing,
        "only_in_upstream": only_upstream,
        "by_category": {
            c: {
                "upstream": len(up_by_cat.get(c, [])),
                "canonical": len(canon_by_cat.get(c, [])),
                "added": sorted(set(canon_by_cat.get(c, [])) - set(up_by_cat.get(c, []))),
            }
            for c in canon_by_cat
        },
    }


# ---------------------------------------------------------------------------
# Data fields
# ---------------------------------------------------------------------------

def diff_data_fields() -> Dict:
    region_reports: List[Dict] = []
    for region, universe in DEFAULT_UNIVERSES.items():
        # Look for the upstream snapshot we copied in for USA, and any other
        # files following the upstream cache naming convention.
        candidates = [
            os.path.join(CONST_DIR, f"upstream_data_fields_{region}_{universe}.json"),
            os.path.join(CONST_DIR, f"data_fields_cache_{region}_1_{universe}.json"),
        ]
        path = next((p for p in candidates if os.path.exists(p)), None)
        if path is None:
            region_reports.append({
                "region": region, "universe": universe,
                "status": "no-cache", "fields": 0, "missing_categories": EXPECTED_CATEGORIES,
            })
            continue

        with open(path) as f:
            try:
                fields = json.load(f)
            except json.JSONDecodeError:
                fields = []
        if not isinstance(fields, list):
            fields = []

        present = set(data_fields_by_category(fields).keys())
        region_reports.append({
            "region": region, "universe": universe,
            "status": "ok" if fields else "empty",
            "fields": len(fields),
            "categories_present": sorted(present),
            "missing_categories": [c for c in EXPECTED_CATEGORIES if c not in present],
        })

    return {
        "pv_baseline_count": len(PV_STANDARD_FIELDS),
        "group_baseline_count": len(GROUP_FIELDS),
        "regions": region_reports,
    }


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def diff_templates() -> Dict:
    # The upstream miner's only hardcoded templates are the four fallbacks in
    # core/template_generator.py::_generate_fallback_template.
    upstream_hardcoded = [
        "ts_rank(close, 20)",
        "-ts_rank(close - ts_mean(close, 20), 10)",
        "ts_rank(volume, 20)",
    ]
    return {
        "upstream_hardcoded_count": len(upstream_hardcoded),
        "canonical_alpha101": len(ALPHA_101),
        "canonical_classical": len(CLASSICAL_FACTORS),
        "canonical_total": len(ALL_TEMPLATES),
        "added": len(ALL_TEMPLATES) - len(upstream_hardcoded),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    report = {
        "operators": diff_operators(),
        "data_fields": diff_data_fields(),
        "templates": diff_templates(),
    }

    out = []
    out.append("=" * 70)
    out.append("WorldQuant Mining - Gap Analysis (upstream vs canonical)")
    out.append("=" * 70)

    op = report["operators"]
    out.append(f"\n[Operators]  upstream={op['upstream_count']}  canonical={op['canonical_count']}  "
               f"added={len(op['added_to_canonical'])}")
    for cat, info in op["by_category"].items():
        out.append(f"  - {cat:<18} upstream={info['upstream']:<3}  canonical={info['canonical']:<3}  "
                   f"added={len(info['added'])}")

    df = report["data_fields"]
    out.append(f"\n[Data Fields]  PV baseline={df['pv_baseline_count']}  "
               f"GROUP baseline={df['group_baseline_count']}")
    for r in df["regions"]:
        out.append(f"  - {r['region']:<3} ({r['universe']}): status={r['status']:<8} "
                   f"fields={r['fields']:<5} missing_categories={len(r['missing_categories'])}")

    tp = report["templates"]
    out.append(f"\n[Templates]  upstream_hardcoded={tp['upstream_hardcoded_count']}  "
               f"canonical={tp['canonical_total']} (alpha101={tp['canonical_alpha101']}, "
               f"classical={tp['canonical_classical']})")

    out.append("=" * 70)
    print("\n".join(out))

    json_path = os.path.join(REPO_ROOT, "GAP_REPORT.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull JSON report written to {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
