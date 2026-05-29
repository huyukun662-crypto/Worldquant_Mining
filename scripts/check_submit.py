"""Check-submit (NOT submit) D0 alpha candidates on WorldQuant Brain.

For each curated D0 candidate this script:
  1. POST /simulations with settings.delay = 0  (consumes a simulation slot),
     polls until COMPLETE, gets an alpha_id.
  2. GET /alphas/{id}            -> IS metrics + is.checks[] (the submit gates).
  3. GET /alphas/{id}/correlations/self  -> max self-correlation.
     GET /alphas/{id}/correlations/prod  -> max production correlation.
  4. Decides `submittable` = no is.check is FAIL, self_corr < SELF_CORR_LIMIT,
     sharpe > SHARPE_FLOOR, turnover < TURNOVER_CEILING.

It DELIBERATELY never calls POST /alphas/{id}/submit -- this is a read-only
"would it pass submission?" probe. Results -> WQ_D0_CHECK_REPORT.json.

Usage:
    python scripts/check_submit.py                 # all curated candidates
    python scripts/check_submit.py "rank(close)"   # ad-hoc expression(s)
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("check_submit")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# ---- submit gates (WQ-authoritative thresholds, per CLAUDE.md) ----
SHARPE_FLOOR = 1.25
TURNOVER_CEILING = 0.25
SELF_CORR_LIMIT = 0.70

# delay=0 base settings; per-candidate `settings` are merged on top.
BASE_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 0,                 # <-- D0
    "decay": 4,
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


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _max_corr(session, alpha_id: str, kind: str):
    """GET /alphas/{id}/correlations/{kind} and extract the max correlation.

    The endpoint returns asynchronously-computed data; shape varies, so we
    parse defensively. Returns (max_corr | None, raw_status).
    """
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/{kind}"
    try:
        r = session.get(url, timeout=30)
    except Exception as e:  # network
        return None, f"err:{e}"
    if r.status_code == 429:
        time.sleep(20)
        return _max_corr(session, alpha_id, kind)
    if r.status_code != 200:
        return None, f"http:{r.status_code}"
    try:
        data = r.json()
    except Exception:
        return None, "no-json"
    if not data:
        return None, "empty"
    # Common shapes: {"max": x}, {"records":[[...,corr], ...], "schema":...},
    # {"min":..,"max":..}. Pull every float and take the abs-max in [-1,1].
    cand = []

    def walk(o):
        if isinstance(o, (int, float)):
            if -1.000001 <= o <= 1.000001:
                cand.append(float(o))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    if isinstance(data, dict) and isinstance(data.get("max"), (int, float)):
        return float(data["max"]), "ok"
    walk(data)
    if not cand:
        return None, "no-corr-values"
    return max(abs(c) for c in cand), "ok"


def check_one(submit_one, session, name: str, expr: str, settings: dict) -> dict:
    s = dict(BASE_SETTINGS)
    s.update(settings or {})
    res = submit_one(session, expr, s)

    rec = {"name": name, "expression": expr, "settings": s,
           "alpha_id": res.get("alpha_id"), "submittable": False}

    if not res.get("ok"):
        rec["ok"] = False
        rec["error"] = f"{res.get('stage')}: {res.get('message') or res.get('body') or res.get('error') or ''}"[:300]
        return rec

    a = res["alpha"]
    is_ = a.get("is", {}) or {}
    checks = is_.get("checks", []) or []
    rec.update({
        "ok": True,
        "sharpe": is_.get("sharpe"),
        "turnover": is_.get("turnover"),
        "fitness": is_.get("fitness"),
        "returns": is_.get("returns"),
        "drawdown": is_.get("drawdown"),
        "longCount": is_.get("longCount"),
        "shortCount": is_.get("shortCount"),
        "checks": [{"name": c.get("name"), "result": c.get("result"),
                    "value": c.get("value"), "limit": c.get("limit")}
                   for c in checks],
    })

    # Self / production correlation (read-only, free).
    self_corr, self_st = _max_corr(session, res["alpha_id"], "self")
    prod_corr, prod_st = _max_corr(session, res["alpha_id"], "prod")
    rec["self_corr"] = self_corr
    rec["self_corr_status"] = self_st
    rec["prod_corr"] = prod_corr
    rec["prod_corr_status"] = prod_st

    # Submittable gate.
    any_fail = any(c.get("result") == "FAIL" for c in checks)
    sh = rec["sharpe"] or 0.0
    to = rec["turnover"] if rec["turnover"] is not None else 1.0
    sc_ok = (self_corr is None) or (self_corr < SELF_CORR_LIMIT)
    rec["submittable"] = bool(
        (not any_fail)
        and sh > SHARPE_FLOOR
        and to < TURNOVER_CEILING
        and sc_ok
    )
    rec["fail_reasons"] = _why(checks, sh, to, self_corr)
    return rec


def _why(checks, sh, to, self_corr):
    r = []
    fails = [c.get("name") for c in checks if c.get("result") == "FAIL"]
    if fails:
        r.append("FAILED_CHECKS=" + ",".join(fails))
    if sh <= SHARPE_FLOOR:
        r.append(f"sharpe {sh:.3f} <= {SHARPE_FLOOR}")
    if to >= TURNOVER_CEILING:
        r.append(f"turnover {to:.3f} >= {TURNOVER_CEILING}")
    if self_corr is not None and self_corr >= SELF_CORR_LIMIT:
        r.append(f"self_corr {self_corr:.3f} >= {SELF_CORR_LIMIT}")
    return r


def probe_delay0(submit_one, session) -> bool:
    """One cheap delay=0 simulation to confirm D0 is enabled on this tier."""
    log.info("=== delay=0 probe: rank(close) ===")
    res = submit_one(session, "rank(close)", dict(BASE_SETTINGS))
    if res.get("ok"):
        log.info("   delay=0 probe OK")
        return True
    msg = (res.get("message") or res.get("body") or res.get("error") or "")
    log.error(f"   delay=0 probe FAILED: stage={res.get('stage')} "
              f"status={res.get('status')} msg={msg[:300]}")
    return False


def main():
    sa = _load(REPO / "scripts" / "submit_alpha.py", "submit_alpha")
    submit_one = sa.submit_one

    # Candidates: ad-hoc from argv, else the curated list.
    if len(sys.argv) > 1:
        cands = [{"name": f"adhoc{i}", "expression": e, "theme": "", "settings": {}}
                 for i, e in enumerate(sys.argv[1:], 1)]
    else:
        dc = _load(REPO / "scripts" / "d0_candidates.py", "d0_candidates")
        cands = dc.CANDIDATES

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    if not probe_delay0(submit_one, cm.session):
        log.error("ABORT: delay=0 not available on this account. "
                  "Reporting probe response to user; no further D0 sims run.")
        return 3

    results = []
    for i, c in enumerate(cands, 1):
        log.info(f"=== [{i}/{len(cands)}] {c['name']}: {c['expression']} ===")
        rec = check_one(submit_one, cm.session, c["name"],
                        c["expression"], c.get("settings", {}))
        rec["theme"] = c.get("theme", "")
        results.append(rec)
        mark = "SUBMITTABLE" if rec.get("submittable") else ("OK " if rec.get("ok") else "ERR")
        log.info(f"   [{mark}] sh={rec.get('sharpe')} to={rec.get('turnover')} "
                 f"fit={rec.get('fitness')} self_corr={rec.get('self_corr')} "
                 f"reasons={rec.get('fail_reasons') or rec.get('error','')}")

    out = REPO / "WQ_D0_CHECK_REPORT.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"wrote {out}")

    print()
    print("=" * 100)
    print(f"{'#':<3}{'status':<12}{'SH':>7}{'TO':>7}{'FIT':>7}{'selfC':>7}  name / expression")
    for i, r in enumerate(results, 1):
        st = "SUBMITTABLE" if r.get("submittable") else ("OK" if r.get("ok") else "ERR")

        def fmt(x):
            return f"{x:7.3f}" if isinstance(x, (int, float)) else "   -   "
        print(f"{i:<3}{st:<12}{fmt(r.get('sharpe'))}{fmt(r.get('turnover'))}"
              f"{fmt(r.get('fitness'))}{fmt(r.get('self_corr'))}  "
              f"{r.get('name')}: {r.get('expression')[:55]}")
        if not r.get("ok"):
            print(f"       └─ {r.get('error','')[:90]}")
        elif not r.get("submittable") and r.get("fail_reasons"):
            print(f"       └─ {'; '.join(r['fail_reasons'])[:90]}")
    print("=" * 100)
    n_sub = sum(1 for r in results if r.get("submittable"))
    print(f"{n_sub} submittable candidate(s) (is.checks all non-FAIL, "
          f"SH>{SHARPE_FLOOR}, TO<{TURNOVER_CEILING}, self_corr<{SELF_CORR_LIMIT}).")
    print("NOTE: nothing was submitted. POST /alphas/{id}/submit was never called.")


if __name__ == "__main__":
    sys.exit(main() or 0)
