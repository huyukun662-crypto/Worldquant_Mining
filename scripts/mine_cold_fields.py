"""Mine 5 alpha factors using "cold" (uncommon) WQ data fields.

Avoids price-volume entirely.  Each candidate uses a distinct cold
field family.  Pipeline:

    1. Submit ALL candidates to WQ Brain /simulations.
    2. Poll /alphas/{id}/correlations/self for each.
    3. Rank by WQ Brain IS Sharpe with hard turnover<0.25 cap.
    4. Write the top 5 to WQ_COLD_FACTORS.json (full metadata).

Run:
    python scripts/mine_cold_fields.py
"""

from __future__ import annotations
import importlib.util
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cold-mine")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
    "delay":          1,
    "universe":       "TOP3000",
    "pasteurization": "ON",
}


# Each candidate: (family, expression, overrides)
# Settings overrides only need to deviate from the FIXED defaults above.
CANDIDATES: list[tuple[str, str, dict]] = [
    # 1. Put/Call open-interest skew (option positioning)
    # Idea: when short-term P/C OI ratio spikes vs long-term baseline,
    # the option-positioning is fear-heavy => buy the dip (contrarian).
    ("pcr_oi",
     "skew = ts_backfill(pcr_oi_30, 10) - ts_backfill(pcr_oi_180, 10);\n"
     "-zscore(ts_decay_linear(skew, 10))",
     {"decay": 0, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    ("pcr_oi",
     "spike = ts_backfill(pcr_oi_10, 5) - ts_backfill(pcr_oi_90, 20);\n"
     "gate = ts_rank(abs(spike), 60) > 0.85;\n"
     "trade_when(gate, -rank(spike), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "INDUSTRY"}),

    # 2. Short-interest sentiment (mdl177_5shortsentimentfactor)
    # Idea: high days_to_cover + rising short interest => squeeze risk.
    # Take the opposite side of crowded shorts (high sht_int means
    # ranked low after the negative sign).
    ("short_sent",
     "si = ts_backfill(mdl177_5shortsentimentfactor_sht_int, 20);\n"
     "dtc = ts_backfill(mdl177_5shortsentimentfactor_days_to_cover, 20);\n"
     "-rank(zscore(si) + zscore(dtc))",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    ("short_sent",
     "util = ts_backfill(mdl177_5shortsentimentfactor_act_util, 10);\n"
     "fee  = ts_backfill(mdl177_5shortsentimentfactor_benchmark_fee, 10);\n"
     "-rank(ts_zscore(util, 60) + ts_zscore(fee, 60))",
     {"decay": 6, "truncation": 0.02, "neutralization": "INDUSTRY"}),

    # 3. Insider news (RavenPack)
    # Idea: rp_css_insider tracks the company-sentiment-score from
    # insider-related news; rp_ess_insider tracks event-sentiment-score.
    # Combine the two with a short decay.
    ("insider_news",
     "css = ts_backfill(rp_css_insider, 20);\n"
     "ess = ts_backfill(rp_ess_insider, 20);\n"
     "rank(ts_decay_linear(css + 0.5 * ess, 10))",
     {"decay": 4, "truncation": 0.02, "neutralization": "INDUSTRY"}),

    ("insider_news",
     "nip = ts_backfill(rp_nip_insider, 20);\n"
     "gate = ts_rank(nip, 60) > 0.80;\n"
     "trade_when(gate, rank(ts_backfill(rp_css_insider, 20)), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 4. Social-media sentiment (StockTwits/scl12 + Thomson Reuters/snt)
    # Idea: rising buzz with positive sentiment => attention-driven up.
    # Use the *_fast_d1 family which is delay=1 native.
    ("social",
     "sent = ts_backfill(scl12_sentiment_fast_d1, 10);\n"
     "buzz = ts_backfill(scl12_buzz_fast_d1, 10);\n"
     "rank(ts_decay_linear(sent * sign(buzz - ts_mean(buzz, 60)), 10))",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    ("social",
     "ret = ts_backfill(snt_buzz_ret_fast_d1, 10);\n"
     "val = ts_backfill(snt_value_fast_d1, 10);\n"
     "rank(ts_decay_linear(val + 0.3 * ret, 10))",
     {"decay": 4, "truncation": 0.02, "neutralization": "INDUSTRY"}),

    # 5. Analyst-estimate dispersion (uncertainty premium)
    # Idea: high cross-analyst dispersion = lottery/uncertainty
    # => underperforms (Diether-Malloy-Scherbina 2002).
    ("dispersion",
     "ed = ts_backfill(fy1_eps_estimate_dispersion_2, 20);\n"
     "sd = ts_backfill(sales_estimate_dispersion, 20);\n"
     "-rank(zscore(ed) + zscore(sd))",
     {"decay": 12, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    ("dispersion",
     "ed = ts_backfill(fy2_eps_estimate_dispersion, 20);\n"
     "delta = ts_delta(ed, 5);\n"
     "-rank(ts_decay_linear(delta, 10))",
     {"decay": 6, "truncation": 0.02, "neutralization": "INDUSTRY"}),
]


POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 5


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class CandidateResult:
    ok: bool
    family: str
    expression: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    margin: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    self_corr: float | None = None
    self_corr_peer: str | None = None
    self_corr_peer_sharpe: float | None = None
    checks: list = field(default_factory=list)
    alpha_id: str = ""
    error: str = ""


def submit(session, family: str, expression: str, settings: dict) -> CandidateResult:
    full = dict(FIXED_SETTINGS); full.update(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expression}

    for attempt in range(6):
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait); continue
        break
    if r.status_code != 201:
        return CandidateResult(ok=False, family=family, expression=expression,
                                settings=full,
                                error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return CandidateResult(ok=False, family=family, expression=expression,
                                settings=full, error="no Location header")

    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st == "COMPLETE":
            alpha_id = data.get("alpha", "")
            ra = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                timeout=30)
            if ra.status_code != 200:
                return CandidateResult(ok=False, family=family,
                                        expression=expression, settings=full,
                                        alpha_id=alpha_id,
                                        error=f"alpha-get-{ra.status_code}")
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            return CandidateResult(
                ok=True, family=family, expression=expression, settings=full,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                margin=float(isb.get("margin") or 0.0),
                longCount=int(isb.get("longCount") or 0),
                shortCount=int(isb.get("shortCount") or 0),
                checks_passed=sum(1 for c in checks
                                   if c.get("result") == "PASS"),
                checks_total=len(checks),
                checks=checks,
                alpha_id=alpha_id,
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return CandidateResult(ok=False, family=family,
                                    expression=expression, settings=full,
                                    error=f"sim-{st}: {data.get('message','')[:300]}")
    return CandidateResult(ok=False, family=family, expression=expression,
                            settings=full, error="poll-timeout")


def fetch_self_corr(session, alpha_id: str, timeout_s: int = 90):
    """Returns (max_abs_corr, top_record_or_None, status)."""
    t0 = time.time()
    while True:
        try:
            r = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self",
                timeout=30)
        except Exception as e:
            return None, None, f"ERROR:{e}"
        if r.status_code in (202, 204) or not r.text.strip():
            if time.time() - t0 > timeout_s: return None, None, "PENDING"
            time.sleep(5); continue
        if r.status_code == 429:
            time.sleep(15); continue
        if r.status_code != 200:
            return None, None, f"ERROR:{r.status_code}"
        try:
            data = r.json()
        except Exception:
            if time.time() - t0 > timeout_s: return None, None, "PENDING"
            time.sleep(5); continue
        sprops = (data.get("schema") or {}).get("properties") or []
        col = {p["name"]: i for i, p in enumerate(sprops)
                if isinstance(p, dict) and "name" in p}
        recs = data.get("records") or []
        top = None
        max_corr = None
        for row in recs:
            if not isinstance(row, list): continue
            if not {"id", "correlation"} <= col.keys(): continue
            corr = row[col["correlation"]]
            if not isinstance(corr, (int, float)): continue
            if max_corr is None or abs(corr) > abs(max_corr):
                max_corr = float(corr)
                top = {
                    "id": row[col["id"]],
                    "correlation": corr,
                    "sharpe": row[col["sharpe"]] if "sharpe" in col else None,
                }
        if max_corr is None and isinstance(data.get("max"), (int, float)):
            max_corr = float(data["max"])
        if max_corr is not None:
            return max_corr, top, "DONE"
        if time.time() - t0 > timeout_s: return None, None, "PENDING"
        time.sleep(5)


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    results: list[CandidateResult] = []
    out_path = REPO / "WQ_COLD_FACTORS.json"

    for i, (family, expr, settings) in enumerate(CANDIDATES, 1):
        log.info(f"=== [{i}/{len(CANDIDATES)}] family={family} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
        res = submit(cm.session, family, expr, settings)
        results.append(res)
        if not res.ok:
            log.warning(f"   FAILED: {res.error[:160]}")
        else:
            log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        with open(out_path, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

    log.info("=== pass 2: self-correlation ===")
    for r in results:
        if not r.ok or not r.alpha_id: continue
        sc, top, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=90)
        r.self_corr = sc
        if top:
            r.self_corr_peer = top.get("id")
            r.self_corr_peer_sharpe = top.get("sharpe")
        sc_s = f"{sc:.3f}" if sc is not None else "?"
        peer = f"{top['id']}@SH{top['sharpe']}" if top else "(none)"
        log.info(f"   {r.alpha_id} self_corr={sc_s} ({st}) peer={peer}")
    with open(out_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    # Selection: pass turnover cap, pass-or-likely-pass self-corr.
    def sc_pass(r):
        if r.self_corr is None: return False
        if abs(r.self_corr) < 0.70: return True
        return (isinstance(r.self_corr_peer_sharpe, (int, float))
                and r.sharpe >= 1.10 * r.self_corr_peer_sharpe)

    eligible = [r for r in results
                 if r.ok and r.turnover < 0.25 and sc_pass(r)]
    eligible.sort(key=lambda r: r.sharpe, reverse=True)
    top5 = eligible[:5]

    print()
    print("=" * 120)
    print(f"All trials OK: {sum(1 for r in results if r.ok)}/{len(results)}")
    print(f"Eligible (TO<0.25 AND self_corr passes): {len(eligible)}")
    print(f"{'#':<3}{'family':<14}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} "
           "alpha_id   expr_brief")
    for i, r in enumerate(eligible[:15], 1):
        marker = "★" if i <= 5 else " "
        first_line = r.expression.split("\n")[-1][:60]
        sc = f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{marker}{i:<2}{r.family:<14}{r.sharpe:7.3f}{r.turnover:7.3f}"
               f"{r.fitness:7.3f} {r.checks_passed:>2}/{r.checks_total:<2}"
               f"{sc:>7} {r.alpha_id:<10} {first_line}")
    print("=" * 120)

    # Final delivery: top 5 + their expressions + settings, condensed.
    delivery = {
        "selected": [
            {
                "rank": i + 1,
                "family": r.family,
                "alpha_id": r.alpha_id,
                "sharpe": r.sharpe,
                "turnover": r.turnover,
                "fitness": r.fitness,
                "returns": r.returns,
                "drawdown": r.drawdown,
                "checks_passed": r.checks_passed,
                "checks_total": r.checks_total,
                "self_corr": r.self_corr,
                "self_corr_peer": r.self_corr_peer,
                "self_corr_peer_sharpe": r.self_corr_peer_sharpe,
                "expression": r.expression,
                "settings": {k: r.settings[k] for k in
                             ("universe", "delay", "decay", "truncation",
                              "neutralization", "pasteurization")},
            }
            for i, r in enumerate(top5)
        ],
        "all_trials": [asdict(r) for r in results],
    }
    with open(out_path, "w") as f:
        json.dump(delivery, f, indent=2)
    log.info(f"wrote {out_path}: {len(top5)} delivered factors")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
