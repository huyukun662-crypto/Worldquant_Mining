"""D0 rare-field pool.

Sources WQ-Brain field IDs from the per-slice cache
`constants/data_fields_cache_USA_0_<UNIVERSE>.json`. "Rare" = low
`alphaCount` (how many submitted alphas already use the field) — fields
in the bottom decile of usage are preferred to satisfy the user's
"冷门字段" requirement.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO / "constants"


def _load_slice(universe: str) -> List[dict]:
    p = CACHE_DIR / f"data_fields_cache_USA_0_{universe}.json"
    with open(p) as f:
        return json.load(f)


def rare_pool(universe: str = "TOP3000",
              max_alpha_count: int = 50,
              categories: tuple = ("news", "option", "analyst",
                                    "socialmedia", "fundamental"),
              types: tuple = ("MATRIX",)) -> Dict[str, List[str]]:
    """Return {category -> [field_id...]} of rare D0 fields.

    Filters:
      - alphaCount <= max_alpha_count  (rarity per user's "冷门字段")
      - coverage >= 0.5                (avoid sparsely-defined fields)
      - type in `types`                (MATRIX only by default — VECTOR
        and event-type fields break ts_corr / arithmetic ops with
        "does not support event inputs" errors)

    The PV category is intentionally excluded — those are the crowded fields.
    """
    fields = _load_slice(universe)
    out: Dict[str, List[str]] = {c: [] for c in categories}
    for f in fields:
        cat = (f.get("category") or {}).get("id", "")
        if cat not in categories:
            continue
        if f.get("type") not in types:
            continue
        ac = f.get("alphaCount") or 0
        cov = f.get("coverage") or 0
        if ac > max_alpha_count or cov < 0.5:
            continue
        out[cat].append(f["id"])
    return out


def flat_rare(universe: str = "TOP3000",
              max_alpha_count: int = 50,
              per_cat: int = 30,
              seed: int = 0) -> List[str]:
    """Flat list, capped per category, shuffled deterministically."""
    rng = random.Random(seed)
    pool = rare_pool(universe, max_alpha_count=max_alpha_count)
    out: List[str] = []
    for cat, ids in pool.items():
        rng.shuffle(ids)
        out.extend(ids[:per_cat])
    rng.shuffle(out)
    return out


if __name__ == "__main__":
    pool = rare_pool()
    for cat, ids in pool.items():
        print(f"{cat:15s}  {len(ids):4d}  e.g. {ids[:3]}")
    print(f"\nflat (per_cat=20): {len(flat_rare(per_cat=20))}")
