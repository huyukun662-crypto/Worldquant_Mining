"""
Canonical WorldQuant Brain data field catalog.

Most data fields on WorldQuant Brain are private and live only behind the
authenticated API; the upstream miner caches them per-(region, delay,
universe) under `constants/data_fields_cache_*.json`. In the snapshot we
imported, only the USA TOP3000 cache was populated — every other region
was an empty list.

This module contains:

1. `PV_STANDARD_FIELDS` — the universe-agnostic price/volume primitives that
   are guaranteed to exist for every WorldQuant equity universe (open, high,
   low, close, volume, vwap, returns, cap, adv*, sharesout, etc.). These are
   the building blocks the 101 Formulaic Alphas paper assumes.

2. Helpers (`load_region_cache`, `data_fields_by_category`) for loading and
   slicing the upstream JSON caches.

3. `EXPECTED_CATEGORIES` — the documented top-level data-field categories,
   used by `compare.py` to flag empty/under-populated regions.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Universe-agnostic Price/Volume primitives (always available on Brain)
# ---------------------------------------------------------------------------

def _pv(id_: str, description: str, type_: str = "MATRIX") -> Dict:
    return {
        "id": id_,
        "description": description,
        "dataset": {"id": "pv1", "name": "Pricing/Volume"},
        "category": {"id": "pv", "name": "Price/Volume"},
        "subcategory": {"id": "pv-price-volume", "name": "Price/Volume"},
        "type": type_,
    }


PV_STANDARD_FIELDS: List[Dict] = [
    _pv("open", "Daily opening price (split- and dividend-adjusted)."),
    _pv("high", "Daily high price."),
    _pv("low", "Daily low price."),
    _pv("close", "Daily closing price."),
    _pv("vwap", "Volume-weighted average price."),
    _pv("volume", "Daily traded share volume."),
    _pv("returns", "Daily simple return: close / ts_delay(close, 1) - 1."),
    _pv("cap", "Market capitalization (shares outstanding * close)."),
    _pv("sharesout", "Total common shares outstanding."),
    _pv("dividend", "Cash dividend per share paid on the date."),
    _pv("split_factor", "Split adjustment factor applied on the date."),
    # Average daily volumes - common Alpha101 inputs
    _pv("adv5",   "Average daily dollar volume over 5 trading days."),
    _pv("adv10",  "Average daily dollar volume over 10 trading days."),
    _pv("adv15",  "Average daily dollar volume over 15 trading days."),
    _pv("adv20",  "Average daily dollar volume over 20 trading days."),
    _pv("adv30",  "Average daily dollar volume over 30 trading days."),
    _pv("adv40",  "Average daily dollar volume over 40 trading days."),
    _pv("adv50",  "Average daily dollar volume over 50 trading days."),
    _pv("adv60",  "Average daily dollar volume over 60 trading days."),
    _pv("adv81",  "Average daily dollar volume over 81 trading days."),
    _pv("adv120", "Average daily dollar volume over 120 trading days."),
    _pv("adv150", "Average daily dollar volume over 150 trading days."),
    _pv("adv180", "Average daily dollar volume over 180 trading days."),
]


# Group / classification fields used as `group` argument to group_* operators
GROUP_FIELDS: List[Dict] = [
    {"id": "industry", "type": "GROUP",
     "description": "GICS / Brain industry classification.",
     "dataset": {"id": "univ1", "name": "Universe"},
     "category": {"id": "pv", "name": "Price/Volume"},
     "subcategory": {"id": "pv-classification", "name": "Classification"}},
    {"id": "sector",   "type": "GROUP",
     "description": "GICS / Brain sector classification.",
     "dataset": {"id": "univ1", "name": "Universe"},
     "category": {"id": "pv", "name": "Price/Volume"},
     "subcategory": {"id": "pv-classification", "name": "Classification"}},
    {"id": "subindustry", "type": "GROUP",
     "description": "GICS / Brain sub-industry classification.",
     "dataset": {"id": "univ1", "name": "Universe"},
     "category": {"id": "pv", "name": "Price/Volume"},
     "subcategory": {"id": "pv-classification", "name": "Classification"}},
    {"id": "country", "type": "GROUP",
     "description": "Country of listing.",
     "dataset": {"id": "univ1", "name": "Universe"},
     "category": {"id": "pv", "name": "Price/Volume"},
     "subcategory": {"id": "pv-classification", "name": "Classification"}},
    {"id": "exchange", "type": "GROUP",
     "description": "Listing exchange.",
     "dataset": {"id": "univ1", "name": "Universe"},
     "category": {"id": "pv", "name": "Price/Volume"},
     "subcategory": {"id": "pv-classification", "name": "Classification"}},
]


# Documented top-level categories of WorldQuant Brain data
EXPECTED_CATEGORIES: List[str] = [
    "pv",            # Price / Volume
    "fundamental",   # Income statement, balance sheet, cash flow
    "analyst",       # Analyst estimates and consensus
    "news",          # News volume, sentiment
    "sentiment",     # Aggregated sentiment
    "socialmedia",   # Reddit / Twitter / etc.
    "option",        # Option chain analytics + IV
    "model",         # Risk / valuation / factor models
    "earnings",      # Reported earnings events
    "macro",         # Macroeconomic series
    "esg",           # Environmental / social / governance
    "shortinterest", # Short interest
    "insider",       # Insider transactions
    "institutional", # Institutional holdings
]


# Documented per-region default universes (matches upstream miner's `region_config`)
DEFAULT_UNIVERSES: Dict[str, str] = {
    "USA": "TOP3000",
    "EUR": "TOP2500",
    "CHN": "TOP2000U",
    "ASI": "MINVOL1M",
    "GLB": "TOP3000",
    "IND": "TOP500",
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

_CACHE_FNAME_FMT = "data_fields_cache_{region}_{delay}_{universe}.json"


def load_region_cache(
    region: str,
    delay: int = 1,
    universe: Optional[str] = None,
    cache_dir: str = "constants",
) -> List[Dict]:
    """Load the upstream JSON cache for (region, delay, universe).

    Returns an empty list if the cache file is missing or empty.
    """
    universe = universe or DEFAULT_UNIVERSES.get(region, "TOP3000")
    fname = _CACHE_FNAME_FMT.format(region=region, delay=delay, universe=universe)
    path = os.path.join(cache_dir, fname)
    if not os.path.exists(path):
        # also try the snapshot we imported
        alt = os.path.join(cache_dir, f"upstream_data_fields_{region}_{universe}.json")
        if os.path.exists(alt):
            path = alt
        else:
            return []
    with open(path, "r") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def data_fields_by_category(fields: Iterable[Dict]) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for fld in fields:
        cat = fld.get("category")
        cat_id = cat.get("id") if isinstance(cat, dict) else (cat or "unknown")
        out.setdefault(cat_id, []).append(fld)
    return out


def data_fields_by_subcategory(fields: Iterable[Dict]) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for fld in fields:
        sub = fld.get("subcategory")
        sub_id = sub.get("id") if isinstance(sub, dict) else (sub or "unknown")
        out.setdefault(sub_id, []).append(fld)
    return out


def missing_categories(fields: Iterable[Dict]) -> List[str]:
    """Return EXPECTED_CATEGORIES not present in `fields`."""
    present = set(data_fields_by_category(fields).keys())
    return [c for c in EXPECTED_CATEGORIES if c not in present]


def merge_with_pv_baseline(fields: List[Dict]) -> List[Dict]:
    """Augment a (possibly empty) cache with the PV+GROUP baseline so that
    downstream code at least has open/high/low/close/volume/etc. to work with.
    """
    have = {f.get("id") for f in fields}
    out = list(fields)
    for f in PV_STANDARD_FIELDS + GROUP_FIELDS:
        if f["id"] not in have:
            out.append(f)
    return out
