"""Sanity tests for the canonical operator / data field / template catalogs."""

from __future__ import annotations

import json
import os
import re

import pytest

from worldquant_mining.operators import (
    CANONICAL_OPERATORS,
    operators_by_category,
    operator_names,
)
from worldquant_mining.data_fields import (
    PV_STANDARD_FIELDS,
    GROUP_FIELDS,
    DEFAULT_UNIVERSES,
    EXPECTED_CATEGORIES,
)
from worldquant_mining.factor_templates import (
    ALPHA_101,
    CLASSICAL_FACTORS,
    ALL_TEMPLATES,
)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM_OPS = os.path.join(REPO_ROOT, "constants", "upstream_operatorRAW.json")


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

def test_canonical_operator_names_unique():
    names = operator_names()
    assert len(names) == len(set(names))


def test_canonical_is_superset_of_upstream():
    with open(UPSTREAM_OPS) as f:
        upstream = json.load(f)
    up_names = {op["name"] for op in upstream}
    canon_names = set(operator_names())
    missing_from_canonical = up_names - canon_names
    assert not missing_from_canonical, (
        f"Canonical catalog dropped upstream operators: {missing_from_canonical}"
    )


def test_each_operator_has_required_keys():
    required = {"name", "category", "scope", "definition", "description"}
    for op in CANONICAL_OPERATORS:
        assert required.issubset(op.keys()), f"missing keys on {op}"
        assert op["category"], op
        assert op["scope"], op
        assert op["definition"], op


def test_operator_categories_match_documented_set():
    documented = {
        "Arithmetic", "Logical", "Time Series", "Cross Sectional",
        "Group", "Transformational", "Vector", "Reduce", "Special",
    }
    cats = set(operators_by_category().keys())
    assert cats == documented, cats


# ---------------------------------------------------------------------------
# Data fields
# ---------------------------------------------------------------------------

def test_pv_baseline_unique_ids():
    ids = [f["id"] for f in PV_STANDARD_FIELDS]
    assert len(ids) == len(set(ids))


def test_pv_baseline_includes_alpha101_inputs():
    needed = {"open", "high", "low", "close", "vwap", "volume", "returns",
              "cap", "adv5", "adv10", "adv15", "adv20", "adv30", "adv40",
              "adv50", "adv60", "adv81", "adv120", "adv150", "adv180"}
    have = {f["id"] for f in PV_STANDARD_FIELDS}
    assert needed.issubset(have), f"missing PV inputs: {needed - have}"


def test_group_fields_present():
    needed = {"sector", "industry", "subindustry"}
    have = {f["id"] for f in GROUP_FIELDS}
    assert needed.issubset(have)


def test_default_universes_cover_all_documented_regions():
    assert set(DEFAULT_UNIVERSES.keys()) >= {"USA", "EUR", "CHN", "ASI", "GLB", "IND"}


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def test_alpha101_count():
    assert len(ALPHA_101) == 101


def test_template_ids_unique():
    ids = [t["id"] for t in ALL_TEMPLATES]
    assert len(ids) == len(set(ids)), "duplicate template ids"


def test_templates_only_use_known_operators_and_fields():
    op_names = set(operator_names())
    pv_ids = {f["id"] for f in PV_STANDARD_FIELDS}
    grp_ids = {f["id"] for f in GROUP_FIELDS}
    known_idents = op_names | pv_ids | grp_ids | {
        # numeric / structural / control words that are NOT identifiers
        "if_else", "and", "or", "not", "true", "false",
    }
    # Anything that looks like an identifier and is followed by '(' should be
    # an operator we know. Pure scalars are ok.
    op_call = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    bad: dict[str, set[str]] = {}
    for t in ALL_TEMPLATES:
        for m in op_call.finditer(t["expression"]):
            ident = m.group(1)
            if ident not in op_names:
                bad.setdefault(t["id"], set()).add(ident)
    assert not bad, f"templates reference unknown operators: {bad}"


def test_templates_have_categories():
    for t in ALL_TEMPLATES:
        assert t.get("category"), t
        assert t.get("expression"), t
