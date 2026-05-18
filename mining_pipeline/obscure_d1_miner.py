"""Obscure-field D1 miner with tunable windows + settings.

Counterpart to `smart_d1_miner.py`, which targets high-alphaCount model
fields. This module is the opposite tail: low-alphaCount, low-userCount
MATRIX fields from the analyst-guidance, fast-d1 social-media, and
seldom-used model categories. These are deliberately *crowded into the
long tail* on the WQ Brain - fewer competing submissions => more
residual alpha.

For each field we sweep TWO setting variants and TWO idiom-windows, so
every field gets 2-4 simulations. That keeps the per-field budget low
while still exposing each candidate to enough parameter freedom to find
its sweet spot.

Run:
    python -m mining_pipeline.obscure_d1_miner --n-fields 12
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("obscure-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "delay":          1,
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
    "pasteurization": "ON",
}


# Curated obscure fields: low-alphaCount/userCount, high-coverage MATRIX
# fields chosen from constants/data_fields_cache_USA_1_TOP3000.json.
# Categories balanced across forward-looking guidance, fast-d1 sentiment,
# and seldom-used model signals.
OBSCURE_FIELDS: list[tuple[str, str]] = [
    # (field_id, theme)
    # Forward-looking analyst guidance (announced corporate targets - very
    # specific shock-style signal)
    ("max_ebitda_guidance",                  "guidance"),
    ("min_capital_expenditure_guidance",     "guidance"),
    ("max_adjusted_net_profit_guidance",     "guidance"),
    ("sales_min_guidance_value",             "guidance"),
    ("min_reported_eps_guidance",            "guidance"),
    # Fast-D1 socialmedia (delay-1 specific sentiment, < 200 alphas)
    ("snt_value_fast_d1",                    "social_fast"),
    ("snt_buzz_fast_d1",                     "social_fast"),
    ("scl12_sentiment_fast_d1",              "social_fast"),
    ("snt_buzz_ret_fast_d1",                 "social_fast"),
    # Long-tail model factors (sub-30 alphaCount specialist signals)
    ("earnings_torpedo_indicator",           "model_tail"),
    ("mdl177_earningsqualityfactor_epschgetr_alt",
                                              "model_tail"),
    ("mdl177_pricemomentumfactor_p50_200ratio_alt",
                                              "model_tail"),
]


# Idioms paired with windows. Each idiom returns a list of expressions
# (one per window). The idea is to let the candidate "try" 2 windows
# in one batch without making the sim count explode.
def idioms_for(fld: str, theme: str) -> list[tuple[str, str, int]]:
    """Return [(name, expression, window), ...] - the 2 idiom-windows to
    test for this (field, theme)."""
    bf = f"ts_backfill({fld}, 240)"  # 240 = ~1 trading year; guidance
                                     #       and earnings are slow data
    out = []
    if theme == "guidance":
        # Guidance shifts are infrequent + sticky - measure delta from a
        # 60-day mean (recent revision) and 250-day mean (annual revision).
        out.append(("ts_av_diff60",  f"rank(ts_av_diff({bf}, 60))",  60))
        out.append(("ts_av_diff250", f"rank(ts_av_diff({bf}, 250))", 250))
    elif theme == "social_fast":
        # Fast-D1 sentiment is high-frequency; mean-revert with short
        # ts_zscore window.
        out.append(("ts_zscore_neg10", f"-ts_zscore({bf}, 10)", 10))
        out.append(("ts_zscore_neg22", f"-ts_zscore({bf}, 22)", 22))
    elif theme == "model_tail":
        # Pre-engineered - just rank with both signs and let the sweep find
        # which side wins.
        out.append(("rank_pos",   f"rank({bf})",  0))
        out.append(("rank_neg",   f"-rank({bf})", 0))
    return out


# Two setting variants per field × idiom (tunability the user asked for).
SETTING_VARIANTS: list[dict] = [
    {"universe": "TOP3000", "neutralization": "INDUSTRY",    "decay": 8,  "truncation": 0.05},
    {"universe": "TOP1000", "neutralization": "SUBINDUSTRY", "decay": 16, "truncation": 0.05},
]


POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 6


@dataclass
class SimResult:
    ok: bool
    expression: str
    settings: dict
    field_: str = ""
    theme: str = ""
    idiom: str = ""
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    checks: list = field(default_factory=list)
    checks_passed: int = 0
    checks_total: int = 0
    all_checks_pass: bool = False
    alpha_id: str = ""
    error: str = ""


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def submit(session, expression: str, settings: dict) -> SimResult:
    full = dict(FIXED_SETTINGS)
    full.update(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expression}

    for attempt in range(5):
        try:
            r = session.post("https://api.worldquantbrain.com/simulations",
                             json=body, timeout=30)
        except Exception as e:
            log.info(f"   POST exc: {e}; sleep 10"); time.sleep(10); continue
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait); continue
        break

    if r.status_code != 201:
        return SimResult(ok=False, expression=expression, settings=full,
                         error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return SimResult(ok=False, expression=expression, settings=full,
                         error="no Location header")

    t0 = time.time()
    last_status = ""
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        try:
            rp = session.get(progress_url, timeout=30)
        except Exception:
            continue
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st != last_status:
            log.info(f"   status={st} ({int(time.time()-t0)}s)")
            last_status = st
        if st == "COMPLETE":
            alpha_id = data.get("alpha")
            try:
                ra = session.get(
                    f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                    timeout=30)
            except Exception as e:
                return SimResult(ok=False, expression=expression, settings=full,
                                 alpha_id=alpha_id or "",
                                 error=f"alpha-get-exc: {e}")
            if ra.status_code != 200:
                return SimResult(ok=False, expression=expression, settings=full,
                                 alpha_id=alpha_id or "",
                                 error=f"alpha-get-{ra.status_code}")
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            passed = [c for c in checks if c.get("result") == "PASS"]
            failed = [c for c in checks if c.get("result") == "FAIL"]
            return SimResult(
                ok=True,
                expression=expression,
                settings=full,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                checks=checks,
                checks_passed=len(passed),
                checks_total=len(checks),
                all_checks_pass=(len(failed) == 0 and len(checks) > 0),
                alpha_id=alpha_id or "",
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return SimResult(ok=False, expression=expression, settings=full,
                             error=f"sim-{st}: {data.get('message','')[:300]}")
    return SimResult(ok=False, expression=expression, settings=full,
                     error="poll-timeout")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-fields", type=int, default=12,
                    help="how many obscure fields to sweep")
    ap.add_argument("--idioms-per-field", type=int, default=1,
                    help="how many idiom-window variants per field (1 or 2)")
    ap.add_argument("--settings-per-expr", type=int, default=1,
                    help="how many setting variants per expression (1 or 2)")
    ap.add_argument("--out", type=str, default="WQ_D1_OBSCURE.json")
    ap.add_argument("--seed", type=int, default=23)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    fields = OBSCURE_FIELDS[:args.n_fields]
    log.info(f"obscure scan: {len(fields)} fields × "
             f"{args.idioms_per_field} idioms × "
             f"{args.settings_per_expr} settings = "
             f"{len(fields) * args.idioms_per_field * args.settings_per_expr} sims")

    rng = random.Random(args.seed)
    results: list[SimResult] = []
    out_path = REPO / args.out
    counter = 0
    for fld, theme in fields:
        idiom_list = idioms_for(fld, theme)[:args.idioms_per_field]
        for name, expr, win in idiom_list:
            settings_subset = SETTING_VARIANTS[:args.settings_per_expr]
            for s in settings_subset:
                counter += 1
                log.info(f"=== obscure {counter} [{theme}] {name}({fld}) "
                         f"uni={s['universe']} neu={s['neutralization']} "
                         f"dec={s['decay']} trc={s['truncation']}")
                log.info(f"   expr: {expr}")
                r = submit(cm.session, expr, s)
                r.field_ = fld
                r.theme = theme
                r.idiom = name
                if r.ok:
                    log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} "
                             f"FIT={r.fitness:+.3f} "
                             f"checks_pass={r.all_checks_pass} "
                             f"({r.checks_passed}/{r.checks_total}) "
                             f"alpha={r.alpha_id}")
                else:
                    log.info(f"   ERR: {r.error[:160]}")
                results.append(r)
                out_path.write_text(json.dumps([asdict(x) for x in results], indent=2))

    ok = [r for r in results if r.ok]
    submit_ready = [r for r in ok if r.all_checks_pass]
    print()
    print("=" * 100)
    print(f"obscure scan done: {len(ok)}/{len(results)} OK; "
          f"submit-ready (all IS checks PASS): {len(submit_ready)}")
    ok.sort(key=lambda r: -abs(r.sharpe))
    for r in ok[:15]:
        print(f"  SH={r.sharpe:+5.2f} TO={r.turnover:.3f} FIT={r.fitness:+5.2f}  "
              f"pass={r.all_checks_pass!s:5s} alpha={r.alpha_id:<10}  "
              f"[{r.theme}] {r.idiom}({r.field_})")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
