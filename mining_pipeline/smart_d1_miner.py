"""Smart D1 alpha miner targeting WorldQuant Brain submission checks.

Previous attempts (mining_pipeline/wq_pipeline.py + expressions.py) only drew
from 10 PV fields (close, open, volume, vwap, ...). PV-only is the most
crowded slice of the WQ alpha space, so those candidates landed in the
0.16-0.42 Sharpe range on WQ Brain - well below the 1.25 submission bar.

This module fixes that gap by:

1. Drawing from the high-coverage MATRIX fields in
   `constants/data_fields_cache_USA_1_TOP3000.json` (USA TOP3000 delay=1)
   across fundamental, analyst, model, socialmedia, sentiment, and pv
   categories - the same families the publicly visible passing-alpha lists
   (CrisperX-50, jglazar/notes) rely on.

2. Wrapping them in simple, robust idioms with cross-sectional / time-series
   stabilization (rank, ts_mean, ts_zscore, ts_av_diff, ts_decay_linear,
   group_rank). Each candidate is composed fresh - it does NOT import
   `worldquant_mining.factor_templates` per the CLAUDE.md spec.

3. Submitting each candidate to /simulations with D1-only settings, sweeping
   universe x neutralization x decay x truncation to maximize chance of
   passing the WQ submission checks (LOW_SHARPE > 1.25, LOW_FITNESS > 1.0,
   LOW_SUB_UNIVERSE_SHARPE > -0.06, CONCENTRATED_WEIGHT, turnover in
   [0.01, 0.7]).

Workflow:
    python -m mining_pipeline.smart_d1_miner --phase scan --n 30
    # ... wait, inspect WQ_D1_SCAN.json
    python -m mining_pipeline.smart_d1_miner --phase refine --top 8 --variants 3
    # ... refined runs land in WQ_D1_REFINED.json
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
from typing import Any, Iterable

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smart-d1")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
FIELD_CACHE = REPO / "constants" / "data_fields_cache_USA_1_TOP3000.json"

# All submissions are D1.
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

# Scan phase: one canonical setting that historically works for fundamental
# / model signals - heavy Industry neutralization, modest decay, low trunc.
SCAN_SETTING = {
    "universe":       "TOP3000",
    "decay":          4,
    "truncation":     0.08,
    "neutralization": "INDUSTRY",
}

# Refine phase: variants to sweep around a winning candidate.
# The scan picks tend to be ts_av_diff(model_field, 20) patterns with
# TO ~0.14-0.25 and FIT ~0.5-0.7. To push FIT past 1.0 we need to cut
# turnover (higher decay) while preserving Sharpe (tight truncation and
# the more granular SUBINDUSTRY neutralization).
REFINE_UNIVERSES     = ["TOP3000", "TOP1000", "TOP500"]
REFINE_NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY"]
REFINE_DECAYS        = [8, 16, 32]
REFINE_TRUNCATIONS   = [0.01, 0.05]


# -----------------------------------------------------------------------
# Candidate generation
# -----------------------------------------------------------------------

# Curated high-coverage MATRIX fields. PV is included but kept short - it
# is the crowded category. Fundamental / analyst / model / socialmedia
# carry most of the residual alpha on this account tier.
FIELD_POOL: dict[str, list[str]] = {
    "pv": [
        "returns", "volume", "vwap", "adv20", "cap", "sharesout",
    ],
    "fundamental": [
        "current_ratio", "return_assets", "sales", "assets", "income",
        "debt_lt", "debt_st", "ebit", "ebitda",
        "fnd6_xad", "fnd6_dcvt", "fnd6_optvol", "fnd6_sppiv",
        "fnd6_pnrsho", "fnd6_mibn",
        "fnd6_newqv1300_invfgq", "fnd6_newqv1300_recdq",
        "fnd6_newqv1300_drltq", "fnd6_newqv1300_rcpq",
        "fnd6_cptnewqv1300_opepsq", "fnd6_newa1v1300_epspi",
        "fnd6_newa1v1300_ibc", "fnd6_newa1v1300_dv",
        "fnd6_cptmfmq_oibdpq", "fnd6_mfma1_invch", "fnd6_txtubend",
        "fnd6_optdrq",
    ],
    "analyst": [
        "anl4_af_eps_value", "anl4_afv4_eps_mean", "anl4_afv4_median_eps",
        "anl4_ebit_value", "anl4_netprofit_value", "anl4_ptp_value",
        "anl4_epsr_value", "actual_eps_value_quarterly",
        "actual_sales_value_quarterly",
    ],
    "model": [
        "mdl177_garpanalystmodel_qgp_vfpriceratio",
        "mdl177_fangma_gpam_usa_fangma_gpam11",
        "mdl177_2_garpanalystmodel_qgp_capeff",
        "mdl177_2_sensitivityfactor400_ttmocfev",
        "mdl177_fangma_rvm_usa_fangma_rvm6",
        "mdl177_2_sensitivityfactor400_chg12msip",
        "mdl177_2_liquidityriskfactor_si_ratio",
        "mdl177_2_deepvaluefactor_curep",
        "mdl177_2_managementqualityfactor_saleicap",
        "mdl177_2_managementqualityfactor_noato",
        "mdl177_deepvaluefactor_curep_alt",
        "mdl177_garpanalystmodel_qgp_capeff",
        "mdl177_garpanalystmodel_qgp_relgrowth",
        "mdl177_5shortsentimentfactor_act_util",
        "mdl177_2_relativevaluemodel_ttmfcfp",
        "mdl177_relativevaluemodel_ttmfcfp",
    ],
    "socialmedia": [
        "scl12_buzz", "snt_buzz", "snt_buzz_bfl", "snt_social_value",
        "snt_social_volume", "snt_buzz_ret", "scl12_sentiment", "snt_value",
    ],
    "news": [
        "news_max_dn_amt", "news_max_up_amt", "news_pct_60min",
        "news_vol_stddev", "news_indx_perf", "news_high_exc_stddev",
        "news_low_exc_stddev", "news_max_dn_ret",
    ],
}


def _idiom_static(field_: str, sign: int) -> str:
    """Cross-sectional rank with sign. ts_backfill drapes over missing
    values so model/fundamental fields with stale-as-of-quarterly cadence
    don't blow up the trading book."""
    sgn = "" if sign > 0 else "-"
    return f"{sgn}rank(ts_backfill({field_}, 120))"


def _idiom_ts_mean(field_: str, sign: int, window: int) -> str:
    sgn = "" if sign > 0 else "-"
    return f"{sgn}rank(ts_mean(ts_backfill({field_}, 120), {window}))"


def _idiom_ts_zscore(field_: str, sign: int, window: int) -> str:
    sgn = "" if sign > 0 else "-"
    return f"{sgn}ts_zscore(ts_backfill({field_}, 120), {window})"


def _idiom_ts_av_diff(field_: str, sign: int, window: int) -> str:
    """Difference between current value and trailing average -
    canonical momentum/reversal building block."""
    sgn = "" if sign > 0 else "-"
    return f"{sgn}rank(ts_av_diff(ts_backfill({field_}, 120), {window}))"


def _idiom_ts_delta(field_: str, sign: int, window: int) -> str:
    sgn = "" if sign > 0 else "-"
    return f"{sgn}rank(ts_delta(ts_backfill({field_}, 120), {window}))"


def _idiom_ts_decay(field_: str, sign: int, window: int) -> str:
    """Linear decay (low-pass) of the raw field, then cross-sectional rank."""
    sgn = "" if sign > 0 else "-"
    return f"{sgn}rank(ts_decay_linear(ts_backfill({field_}, 120), {window}))"


def _idiom_group_rank(field_: str, sign: int) -> str:
    """Within-industry rank: by construction passes industry-neutralization
    sanity since it already partitions risk."""
    sgn = "" if sign > 0 else "-"
    return f"{sgn}group_rank(ts_backfill({field_}, 120), subindustry)"


def _idiom_grouped_zscore(field_: str, sign: int, window: int) -> str:
    sgn = "" if sign > 0 else "-"
    return f"{sgn}group_zscore(ts_mean(ts_backfill({field_}, 120), {window}), industry)"


@dataclass
class Candidate:
    expression: str
    idiom: str
    field_: str
    field_category: str
    sign: int
    window: int = 0


def candidate_pool(pool: dict[str, list[str]], seed: int = 0) -> list[Candidate]:
    """Compose original candidates. Each (field, idiom, sign, window) tuple
    is unique; idiom selection per field is small so we don't blow the
    simulation budget."""
    rng = random.Random(seed)
    cands: list[Candidate] = []
    seen: set[str] = set()

    def add(expr: str, idiom: str, fld: str, cat: str, sign: int, w: int = 0):
        if expr in seen:
            return
        seen.add(expr)
        cands.append(Candidate(expr, idiom, fld, cat, sign, w))

    # For each category, fan out idioms per field. The choice of idioms
    # and windows differs by category to bias toward what works:
    #  - PV: ts_zscore / ts_av_diff with mid-windows (reversal regime)
    #  - fundamental: rank / -rank (level signal) + ts_av_diff (revision)
    #  - analyst / model: rank (already-engineered) and ts_av_diff (trend)
    #  - socialmedia / news: ts_zscore / -ts_mean (mean-reverting noise)

    for fld in pool.get("pv", []):
        add(_idiom_ts_zscore(fld, +1, 20),    "ts_zscore",   fld, "pv", +1, 20)
        add(_idiom_ts_av_diff(fld, -1, 60),   "ts_av_diff",  fld, "pv", -1, 60)

    for fld in pool.get("fundamental", []):
        add(_idiom_static(fld, -1),           "rank_neg",    fld, "fundamental", -1)
        add(_idiom_static(fld, +1),           "rank_pos",    fld, "fundamental", +1)
        add(_idiom_ts_av_diff(fld, +1, 250),  "ts_av_diff",  fld, "fundamental", +1, 250)
        add(_idiom_ts_mean(fld, -1, 10),      "ts_mean_neg", fld, "fundamental", -1, 10)

    for fld in pool.get("analyst", []):
        add(_idiom_static(fld, -1),           "rank_neg",    fld, "analyst", -1)
        add(_idiom_static(fld, +1),           "rank_pos",    fld, "analyst", +1)
        add(_idiom_ts_av_diff(fld, +1, 60),   "ts_av_diff",  fld, "analyst", +1, 60)

    for fld in pool.get("model", []):
        # model fields are typically already z-scored alpha factors,
        # so a plain rank with sign sweep is usually the right wrapper.
        add(_idiom_static(fld, -1),           "rank_neg",    fld, "model", -1)
        add(_idiom_static(fld, +1),           "rank_pos",    fld, "model", +1)
        add(_idiom_ts_av_diff(fld, +1, 20),   "ts_av_diff",  fld, "model", +1, 20)
        add(_idiom_ts_decay(fld, -1, 16),     "ts_decay",    fld, "model", -1, 16)

    for fld in pool.get("socialmedia", []):
        add(_idiom_ts_zscore(fld, -1, 22),    "ts_zscore_neg", fld, "socialmedia", -1, 22)
        add(_idiom_ts_av_diff(fld, -1, 60),   "ts_av_diff",    fld, "socialmedia", -1, 60)

    for fld in pool.get("news", []):
        add(_idiom_ts_zscore(fld, -1, 22),    "ts_zscore_neg", fld, "news", -1, 22)

    # Priority: model > analyst > fundamental > socialmedia > news > pv.
    # Model fields are already-engineered alpha factors so they reach
    # passing-Sharpe at the highest base rate. Within each category we
    # shuffle so we don't bias by field order in the pool dict.
    order = {"model": 0, "analyst": 1, "fundamental": 2,
             "socialmedia": 3, "news": 4, "pv": 5}
    by_cat: dict[str, list[Candidate]] = {}
    for c in cands:
        by_cat.setdefault(c.field_category, []).append(c)
    out: list[Candidate] = []
    for cat in sorted(by_cat, key=lambda k: order.get(k, 99)):
        rng.shuffle(by_cat[cat])
        out.extend(by_cat[cat])
    return out


# -----------------------------------------------------------------------
# WQ Brain submission
# -----------------------------------------------------------------------

@dataclass
class SimResult:
    ok: bool
    expression: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    long_count: int = 0
    short_count: int = 0
    checks: list = field(default_factory=list)
    checks_passed: int = 0
    checks_total: int = 0
    all_checks_pass: bool = False
    alpha_id: str = ""
    error: str = ""
    candidate: dict = field(default_factory=dict)


POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 6


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
            log.info(f"   POST exc: {e}; sleep 10")
            time.sleep(10); continue
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
            # SELF_CORRELATION often PENDING - treat PENDING as not-fail
            # for the "all_checks_pass" flag (it'll resolve at submit time).
            non_pending_fail = [c for c in checks if c.get("result") == "FAIL"]
            return SimResult(
                ok=True,
                expression=expression,
                settings=full,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                long_count=int(isb.get("longCount") or 0),
                short_count=int(isb.get("shortCount") or 0),
                checks=checks,
                checks_passed=len(passed),
                checks_total=len(checks),
                all_checks_pass=(len(non_pending_fail) == 0 and len(checks) > 0),
                alpha_id=alpha_id or "",
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return SimResult(ok=False, expression=expression, settings=full,
                             error=f"sim-{st}: {data.get('message','')[:300]}")
    return SimResult(ok=False, expression=expression, settings=full,
                     error="poll-timeout")


# -----------------------------------------------------------------------
# Phases
# -----------------------------------------------------------------------

def phase_scan(session, n: int, seed: int, out: Path) -> list[SimResult]:
    """Submit each candidate once with the canonical SCAN_SETTING. The
    point is to triage the pool by Sharpe before paying refine cost on
    multiple settings."""
    cands = candidate_pool(FIELD_POOL, seed=seed)[:n]
    log.info(f"scan: {len(cands)} candidates, ~{len(cands)*120/60:.0f} min "
             f"at ~120s/sim with concurrency 1")

    results: list[SimResult] = []
    for i, c in enumerate(cands, 1):
        log.info(f"=== scan {i}/{len(cands)}  [{c.field_category}] {c.idiom}({c.field_}) ===")
        log.info(f"   expr: {c.expression}")
        r = submit(session, c.expression, SCAN_SETTING)
        r.candidate = asdict(c)
        if r.ok:
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                     f"checks_pass={r.all_checks_pass} ({r.checks_passed}/{r.checks_total})  "
                     f"alpha={r.alpha_id}")
        else:
            log.info(f"   ERR: {r.error[:160]}")
        results.append(r)
        # snapshot
        out.write_text(json.dumps([asdict(x) for x in results], indent=2))
    return results


def phase_refine(session, scan_path: Path, top: int, max_variants: int,
                 out: Path) -> list[SimResult]:
    """Pick top-K by |WQ Sharpe| (sign-aware: also recover negative-Sharpe
    candidates whose inverse passes), then sweep universe/neutralization/
    decay/truncation for each."""
    scan_data = json.loads(scan_path.read_text())
    ok = [SimResult(**{k: v for k, v in d.items() if k != "candidate"}, candidate=d.get("candidate", {}))
          for d in scan_data if d.get("ok")]

    # Rank by absolute Sharpe (a strong-negative signal flipped sign yields
    # the same alpha - we'll just flip the sign in the variant).
    ok.sort(key=lambda r: abs(r.sharpe), reverse=True)
    picks = ok[:top]
    log.info(f"refine: {len(picks)} picks chosen by |SH|")

    results: list[SimResult] = []
    for i, base in enumerate(picks, 1):
        # If the scan Sharpe is negative, flip the expression sign
        # for the refine sweep.
        expr = base.expression
        if base.sharpe < 0:
            expr = f"-1 * ({expr})"
            log.info(f"--- refine {i}: flipping sign (scan SH was {base.sharpe:+.3f})")

        # Build variant settings - up to max_variants of them
        variant_settings: list[dict] = []
        for uni in REFINE_UNIVERSES:
            for neu in REFINE_NEUTRALIZATIONS:
                for dec in REFINE_DECAYS:
                    for trc in REFINE_TRUNCATIONS:
                        s = {"universe": uni, "neutralization": neu,
                             "decay": dec, "truncation": trc}
                        variant_settings.append(s)
        rng = random.Random(101 + i)
        rng.shuffle(variant_settings)
        variant_settings = variant_settings[:max_variants]

        for j, s in enumerate(variant_settings, 1):
            log.info(f"=== refine {i}.{j}  expr={expr[:80]}  settings={s}")
            r = submit(session, expr, s)
            r.candidate = base.candidate
            if r.ok:
                log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                         f"checks_pass={r.all_checks_pass} ({r.checks_passed}/{r.checks_total})  "
                         f"alpha={r.alpha_id}")
            else:
                log.info(f"   ERR: {r.error[:160]}")
            results.append(r)
            out.write_text(json.dumps([asdict(x) for x in results], indent=2))
    return results


# -----------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------

def authenticate():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        raise RuntimeError("WQ Brain authentication failed")
    return cm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["scan", "refine"], required=True)
    ap.add_argument("--n", type=int, default=30, help="scan: how many candidates")
    ap.add_argument("--top", type=int, default=6,
                    help="refine: how many scan winners to refine")
    ap.add_argument("--variants", type=int, default=4,
                    help="refine: how many setting variants per pick")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--scan-out", type=str, default="WQ_D1_SCAN.json")
    ap.add_argument("--refine-out", type=str, default="WQ_D1_REFINED.json")
    args = ap.parse_args()

    cm = authenticate()
    log.info(f"authenticated as {cm.credentials.username}")

    if args.phase == "scan":
        out = REPO / args.scan_out
        results = phase_scan(cm.session, args.n, args.seed, out)
        all_pass = [r for r in results if r.ok and r.all_checks_pass]
        winners = [r for r in results if r.ok and r.sharpe > 1.25 and r.turnover < 0.7]
        print()
        print("=" * 100)
        print(f"scan done: {sum(1 for r in results if r.ok)}/{len(results)} OK")
        print(f"  passing-all-checks: {len(all_pass)}")
        print(f"  SH>1.25 & TO<0.7  : {len(winners)}")
        for r in sorted([r for r in results if r.ok], key=lambda x: -x.sharpe)[:10]:
            c = r.candidate
            print(f"  {r.sharpe:+6.2f}  TO={r.turnover:5.3f}  FIT={r.fitness:+5.2f}  "
                  f"pass={r.all_checks_pass!s:5s}  alpha={r.alpha_id:<10}  "
                  f"{c.get('idiom','?')}({c.get('field_','?')})")
        print("=" * 100)

    else:  # refine
        scan_path = REPO / args.scan_out
        if not scan_path.exists():
            log.error(f"scan output {scan_path} not found - run --phase scan first")
            return 2
        out = REPO / args.refine_out
        results = phase_refine(cm.session, scan_path, args.top, args.variants, out)
        all_pass = [r for r in results if r.ok and r.all_checks_pass]
        winners = [r for r in results if r.ok and r.sharpe > 1.25 and r.turnover < 0.7]
        print()
        print("=" * 110)
        print(f"refine done: {sum(1 for r in results if r.ok)}/{len(results)} OK")
        print(f"  passing-all-checks: {len(all_pass)}")
        print(f"  SH>1.25 & TO<0.7  : {len(winners)}")
        print()
        print("SUBMIT-READY (all IS checks pass, SH > 1.25, TO < 0.7):")
        ready = [r for r in winners if r.all_checks_pass]
        ready.sort(key=lambda r: r.sharpe, reverse=True)
        for r in ready:
            s = r.settings
            print(f"  SH={r.sharpe:5.2f}  TO={r.turnover:5.3f}  FIT={r.fitness:5.2f}  "
                  f"alpha={r.alpha_id}  uni={s.get('universe')}  "
                  f"neu={s.get('neutralization')}  dec={s.get('decay')}  trc={s.get('truncation')}  "
                  f"expr={r.expression[:80]}")
        print("=" * 110)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
