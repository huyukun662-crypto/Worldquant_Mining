"""Curate a multi-category data-field pool for the expression generator.

Reads `constants/data_fields_cache_USA_1_TOP3000.json` and emits
`constants/field_pool_USA_TOP3000.json` containing the top-N MATRIX
fields per category, ranked by (coverage * log(1+userCount)).

Per user spec, the pool spans all 8 documented categories (analyst,
fundamental, model, news, option, pv, sentiment, socialmedia) so the
expression generator can compose factors across category boundaries,
not just PV.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "constants" / "data_fields_cache_USA_1_TOP3000.json"
DST = REPO / "constants" / "field_pool_USA_TOP3000.json"

# Per-category budgets. Sum ~150 fields gives Optuna a rich but
# manageable expression space.
BUDGETS = {
    "analyst":      25,
    "fundamental":  25,
    "model":        30,
    "news":         15,
    "option":       15,
    "pv":           20,
    "sentiment":    10,
    "socialmedia":  10,
}

# Coverage floor per category. fundamental/option are sparser by nature.
MIN_COV = {
    "analyst": 0.5, "fundamental": 0.3, "model": 0.5, "news": 0.5,
    "option": 0.3,  "pv": 0.5,          "sentiment": 0.3, "socialmedia": 0.5,
}


def score(f: dict) -> float:
    cov = float(f.get("coverage") or 0.0)
    uc  = float(f.get("userCount") or 0.0)
    ac  = float(f.get("alphaCount") or 0.0)
    return cov * (1.0 + math.log1p(uc) + 0.5 * math.log1p(ac))


def main() -> int:
    fields = json.load(open(SRC))
    pool: dict[str, list[str]] = {}
    for cat, budget in BUDGETS.items():
        thr = MIN_COV[cat]
        cands = [f for f in fields
                 if f["category"]["id"] == cat
                 and f.get("type") == "MATRIX"
                 and float(f.get("coverage") or 0) >= thr]
        cands.sort(key=score, reverse=True)
        pool[cat] = [f["id"] for f in cands[:budget]]
        print(f"{cat:14s} chose {len(pool[cat]):3d} / {len(cands):4d} "
              f"candidates (cov>={thr})")
    total = sum(len(v) for v in pool.values())
    print(f"total fields in pool: {total}")
    DST.write_text(json.dumps(pool, indent=2))
    print(f"wrote {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
