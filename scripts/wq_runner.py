"""Reusable WQ Brain submission runner.

Each "round" is a list of factor dicts:
    {id, category, idea, original, expression, settings_override}

Usage from a round script:

    from wq_runner import run_round, BASE_SETTINGS

    FACTORS = [
        {"id": "QM_R2_01", "category": "...", "idea": "...",
         "original": "...", "expression": "...",
         "settings_override": {"decay": 8}},
        ...
    ]

    if __name__ == "__main__":
        sys.exit(run_round(FACTORS, results_path=Path("WQ_QUANTML_RESULTS.json"),
                           append=True))
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("wq-run")
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 0,
    "neutralization": "INDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

SH_THRESH = 1.25
TO_THRESH = 0.25
FIT_THRESH = 1.0
POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 5


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def authenticate():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        raise RuntimeError("WQ authentication failed")
    return cm


def submit_one(session, expression: str, settings: dict) -> dict:
    body = {"type": "REGULAR", "settings": settings, "regular": expression}
    log.info(f"-> POST /simulations  expr={expression[:80]!r}")
    log.info(
        f"   decay={settings['decay']}  neut={settings['neutralization']}  "
        f"trunc={settings['truncation']}  univ={settings['universe']}"
    )
    r = session.post(
        "https://api.worldquantbrain.com/simulations", json=body, timeout=30
    )
    if r.status_code != 201:
        return {
            "ok": False,
            "stage": "submit",
            "status": r.status_code,
            "body": r.text[:500],
        }
    progress_url = r.headers.get("Location")
    if not progress_url:
        return {"ok": False, "stage": "submit", "error": "no Location"}

    t0 = time.time()
    last_status = ""
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30)
            continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        status = data.get("status", "")
        if status != last_status:
            log.info(f"   status={status} ({int(time.time() - t0)}s)")
            last_status = status
        if status == "COMPLETE":
            alpha_id = data.get("alpha")
            if not alpha_id:
                return {
                    "ok": False,
                    "stage": "complete-no-alpha-id",
                    "data": data,
                }
            ra = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                timeout=30,
            )
            if ra.status_code != 200:
                return {
                    "ok": False,
                    "stage": "alpha-get",
                    "status": ra.status_code,
                    "body": ra.text[:500],
                    "alpha_id": alpha_id,
                }
            return {"ok": True, "alpha_id": alpha_id, "alpha": ra.json()}
        if status in ("ERROR", "FAILED", "WARNING"):
            return {
                "ok": False,
                "stage": "simulation",
                "status": status,
                "message": data.get("message", "")[:500],
                "data": data,
            }
    return {"ok": False, "stage": "timeout"}


def passes_gates(entry: dict) -> bool:
    sh = entry.get("sharpe")
    to = entry.get("turnover")
    fit = entry.get("fitness")
    return (
        isinstance(sh, (int, float))
        and sh > SH_THRESH
        and isinstance(to, (int, float))
        and to < TO_THRESH
        and isinstance(fit, (int, float))
        and fit > FIT_THRESH
    )


def run_round(
    factors: list[dict], results_path: Path, append: bool = True
) -> int:
    cm = authenticate()
    log.info(f"authenticated as {cm.credentials.username}")
    log.info(f"submitting {len(factors)} factors")

    existing = []
    if append and results_path.exists():
        existing = json.loads(results_path.read_text())
    results = list(existing)

    for i, f in enumerate(factors, 1):
        settings = {**BASE_SETTINGS, **f.get("settings_override", {})}
        log.info(
            f"=== [{i}/{len(factors)}] {f['id']}  ({f['category']}) ==="
        )
        res = submit_one(cm.session, f["expression"], settings)
        entry = {
            "id": f["id"],
            "category": f["category"],
            "idea": f.get("idea", ""),
            "original": f.get("original", ""),
            "expression": f["expression"],
            "settings": settings,
            **res,
        }
        if res.get("ok"):
            is_ = res["alpha"].get("is") or {}
            entry["sharpe"] = is_.get("sharpe")
            entry["turnover"] = is_.get("turnover")
            entry["fitness"] = is_.get("fitness")
            entry["returns"] = is_.get("returns")
            entry["drawdown"] = is_.get("drawdown")
            entry["margin"] = is_.get("margin")
            entry["checks"] = is_.get("checks")
            star = " ***" if passes_gates(entry) else ""
            log.info(
                f"   OK alpha_id={res.get('alpha_id')} "
                f"SH={entry['sharpe']} TO={entry['turnover']} "
                f"FIT={entry['fitness']}{star}"
            )
        else:
            log.info(
                f"   ERR stage={res.get('stage')} "
                f"msg={(res.get('message') or res.get('body') or '')[:120]}"
            )
        results.append(entry)
        results_path.write_text(json.dumps(results, indent=2))

    # Final pretty print
    print()
    print("=" * 105)
    print(
        f"{'id':<12}{'cat':<18}{'SH':>7}{'TO':>7}{'FIT':>7}{'RET':>7}  "
        f"alpha_id    expression"
    )
    new_entries = results[len(existing):]
    for r in new_entries:
        def fmt(x):
            return f"{x:7.2f}" if isinstance(x, (int, float)) else "      -"
        if r.get("ok"):
            star = " *" if passes_gates(r) else "  "
            print(
                f"{r['id']:<12}{r['category']:<18}"
                f"{fmt(r.get('sharpe'))}{fmt(r.get('turnover'))}"
                f"{fmt(r.get('fitness'))}{fmt(r.get('returns'))}{star}"
                f" {r['alpha_id']:<11} {r['expression'][:50]}"
            )
        else:
            print(
                f"{r['id']:<12}{r['category']:<18}"
                f"{'-':>7}{'-':>7}{'-':>7}{'-':>7}    ERR        "
                f"{r['expression'][:50]} ({r.get('stage')})"
            )
    print("=" * 105)
    survivors = [r for r in new_entries if r.get("ok") and passes_gates(r)]
    log.info(f"survivors this round: {len(survivors)} / {len(new_entries)}")
    return 0
