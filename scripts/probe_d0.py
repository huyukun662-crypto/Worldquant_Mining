"""D0 access probe — hard gate for the D0 mining pipeline.

Submits trivial expressions to `/simulations` with `delay=0` to verify
whether the authenticated account is permitted to run D0 backtests on
the USA TOP1000 universe (the only universe that exposes D0 fields per
`constants/data_fields_union_USA.json`).

Exits with code 0 iff at least one D0 submission reaches status COMPLETE
without an "Delay 0 is not available" rejection.

Writes `constants/d0_field_universe_matrix.json`:
    {
      "d0_enabled": true|false,
      "tested_at": "...",
      "probes": [{universe, family, expression, ok, status, body, alpha_id}],
      "field_pool_summary": {category: count}
    }
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("probe_d0")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
UNION_PATH = REPO / "constants" / "data_fields_union_USA.json"
OUT_PATH = REPO / "constants" / "d0_field_universe_matrix.json"

# Only TOP1000 carries D0 fields on this account tier; we still probe other
# universes in case the platform accepts D0 submissions with TOP1000-only
# fields under different size buckets.
PROBE_UNIVERSES = ["TOP1000", "TOP3000", "TOP500", "TOP200"]


def _load_module(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _submit_with_retry(submit_mod, session, expression: str,
                        settings: dict, max_retries: int = 8) -> dict:
    """submit_one wrapper that retries on HTTP 429 concurrency rejections.

    The WQ Brain account has a 2-3 concurrent simulation cap; submissions
    while at the cap return 429 immediately (not after polling). Back off
    and retry until the slot frees.
    """
    import time
    backoff = 10
    for attempt in range(max_retries):
        log.info(f"-> submit attempt {attempt+1}/{max_retries} expr={expression[:60]!r} u={settings.get('universe')} d={settings.get('delay')}")
        res = submit_mod.submit_one(session, expression, settings=settings)
        if res.get("ok"):
            return res
        # Retry only on the explicit concurrency 429.
        body = res.get("body") or ""
        if res.get("stage") == "submit" and res.get("status") == 429 \
                and "CONCURRENT_SIMULATION_LIMIT" in body:
            wait = min(backoff, 180)
            log.info(f"   429 concurrency cap; sleeping {wait}s then retry")
            time.sleep(wait)
            backoff = min(backoff * 2, 180)
            continue
        return res
    return res


def _pick_probe_field_per_family(fields: list[dict]) -> dict[str, str]:
    """Return one representative D0 MATRIX field per category."""
    out: dict[str, str] = {}
    for f in fields:
        if f.get("delay") != 0 or f.get("type") != "MATRIX":
            continue
        cat = f["category"]["id"]
        if cat in out:
            continue
        out[cat] = f["id"]
    return out


def main() -> int:
    submit_mod = _load_module(REPO / "scripts" / "submit_alpha.py", "submit_alpha")
    cm_mod = _load_module(VENDOR / "core" / "credential_manager.py", "cm")

    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed - cannot probe")
        return 2
    log.info(f"authenticated as {cm.credentials.username}")

    union = json.load(open(UNION_PATH))
    d0_fields = [f for f in union if f.get("delay") == 0]
    family_probe = _pick_probe_field_per_family(d0_fields)
    log.info(f"D0 field families to probe: {sorted(family_probe)}")

    probes: list[dict] = []
    d0_any_complete = False
    d0_explicitly_blocked = False  # HTTP 400 "Delay 0 is not available"

    # Phase A: basic D0 access — `close` on each universe.
    # Retry on HTTP 429 (concurrency limit) instead of treating it as a block.
    for u in PROBE_UNIVERSES:
        settings = {"universe": u, "delay": 0, "neutralization": "SUBINDUSTRY",
                    "decay": 0, "truncation": 0.08}
        res = _submit_with_retry(submit_mod, cm.session, "close", settings)
        entry = {
            "phase": "access", "universe": u, "family": "pv",
            "expression": "close", "ok": bool(res.get("ok")),
            "stage": res.get("stage"), "status": res.get("status"),
            "body": (res.get("body") or res.get("message") or "")[:300],
            "alpha_id": res.get("alpha_id"),
        }
        probes.append(entry)
        if entry["ok"]:
            d0_any_complete = True
            log.info(f"  D0 access OK on {u} -> {res.get('alpha_id')}")
        else:
            body = entry["body"] or ""
            if entry["status"] == 400 and "Delay 0" in body:
                d0_explicitly_blocked = True
                log.error(f"  D0 EXPLICITLY blocked on {u}: HTTP 400 Delay 0 not available")
            else:
                log.warning(f"  D0 sim not-complete on {u}: stage={entry['stage']} status={entry['status']} body={body[:120]}")
        _persist(probes, d0_any_complete, family_probe, d0_fields)

    if d0_explicitly_blocked and not d0_any_complete:
        log.error("=" * 70)
        log.error("D0 EXPLICITLY BLOCKED (HTTP 400) on this account tier.")
        log.error("Per user spec ('D0 only, refuse D1'), aborting.")
        log.error("Evidence written to %s", OUT_PATH)
        log.error("=" * 70)
        return 1

    if not d0_any_complete:
        log.error("=" * 70)
        log.error("D0 probe failed without explicit 400 block — likely 429/timeout/transient.")
        log.error("Inspect %s for per-universe stage/status details.", OUT_PATH)
        log.error("=" * 70)
        return 3  # distinct exit code: transient, not policy

    # Phase B: family probes on TOP1000 (the only universe with D0 fields).
    for fam, fid in family_probe.items():
        expr = f"rank({fid})"
        settings = {"universe": "TOP1000", "delay": 0,
                    "neutralization": "SUBINDUSTRY",
                    "decay": 4, "truncation": 0.08}
        res = _submit_with_retry(submit_mod, cm.session, expr, settings)
        entry = {
            "phase": "family", "universe": "TOP1000", "family": fam,
            "expression": expr, "ok": bool(res.get("ok")),
            "stage": res.get("stage"), "status": res.get("status"),
            "body": (res.get("body") or res.get("message") or "")[:300],
            "alpha_id": res.get("alpha_id"),
        }
        if res.get("ok"):
            a = res["alpha"]
            is_ = a.get("is", {}) or {}
            entry["sharpe"] = is_.get("sharpe")
            entry["turnover"] = is_.get("turnover")
            entry["fitness"] = is_.get("fitness")
            entry["checks_passed"] = sum(
                1 for c in (is_.get("checks") or []) if c.get("result") == "PASS")
            entry["checks_total"] = len(is_.get("checks") or [])
        probes.append(entry)
        _persist(probes, d0_any_complete, family_probe, d0_fields)

    log.info("D0 probe complete. wrote %s", OUT_PATH)
    return 0


def _persist(probes: list[dict], d0_enabled: bool,
             family_probe: dict[str, str], d0_fields: list[dict]) -> None:
    from collections import Counter
    summary = dict(Counter(
        f["category"]["id"] for f in d0_fields
        if f.get("type") == "MATRIX"))
    out = {
        "d0_enabled": d0_enabled,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "d0_universe": "TOP1000",  # per data_fields_union_USA.json
        "field_pool_summary_matrix": summary,
        "family_probe_fields": family_probe,
        "probes": probes,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
