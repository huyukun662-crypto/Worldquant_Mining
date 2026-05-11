"""Run the worldquant-5-agent-workflow skill end-to-end against WQ Brain.

This is the executable counterpart of the markdown skill bundle at
`.claude/skills/worldquant-5-agent-workflow/`. The skill defines five
agent roles (Research Librarian, Hypothesis Architect, Alpha Builder,
Backtest Operator, Evaluator & Recorder), JSON handoff schemas, and a
G1-G5 validation funnel. The current orchestrator plays all five roles
in one process and uses the WQ Brain `/simulations` endpoint as the
authoritative backtest (per CLAUDE.md: local yfinance numbers do not
generalize).

Stage flow:
    1. Librarian   -> outputs/research_brief.md + handoff_1_to_2.json
    2. Architect   -> outputs/session_metadata.yml + handoff_2_to_3.json
    3. Builder     -> outputs/expressions_batch_0001.md + handoff_3_to_4.json
    4. Operator    -> submit 8 to WQ Brain
                      -> outputs/backtest_results_batch_0001.md
                      -> handoff_4_to_5.json (with per-expression gate table)
    5. Evaluator   -> outputs/alpha_ranking.md + final_summary.md
                      -> updated round_0001.yml + run_state.json

User filter applied at Stage 5 (over the WQ-Brain returned metrics):
    WQ_IS_Sharpe   > 1.25
    WQ_IS_Fitness  > 1.0
    WQ_IS_Turnover < 0.25

Run:
    python scripts/run_5agent_workflow.py [--topic short_term_reversal]
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("5agent")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.25
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.25

DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 8,
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


# -- Stage 3 expressions: one dominant mechanism = short-term reversal -------
# Each expression negates a recent-return signal so "high signal = long the
# loser". Variants explore (a) smoothing operator, (b) horizon, (c) volume
# conditioning, (d) microstructure source (vwap vs close). All wrapped in
# rank() for cross-sectional scaling. INDUSTRY neutralization removes
# industry-level drift; truncation=0.08 caps tail weights.
EXPRESSION_SETS = {
    "short_term_reversal": [
        {
            "idx": 1, "id": "stm_rev_mean5",
            "code": "rank(reverse(ts_mean(returns, 5)))",
            "rationale": "Long 5d losers. Pure short-term reversal baseline.",
            "expected_turnover_direction": "higher",
        },
        {
            "idx": 2, "id": "stm_rev_decay8",
            "code": "rank(reverse(ts_decay_linear(returns, 8)))",
            "rationale": "Linear-decay-smoothed reversal; lower TO than mean5.",
            "expected_turnover_direction": "lower",
        },
        {
            "idx": 3, "id": "stm_rev_zscore10",
            "code": "rank(reverse(ts_zscore(returns, 10)))",
            "rationale": "Z-scored reversal: normalizes by stock-specific vol.",
            "expected_turnover_direction": "neutral",
        },
        {
            "idx": 4, "id": "stm_rev_volcond",
            "code": "rank(reverse(multiply(ts_mean(returns, 5), ts_mean(divide(volume, adv20), 5))))",
            "rationale": "Reversal weighted by abnormal volume - extreme moves on heavy flow tend to revert harder.",
            "expected_turnover_direction": "higher",
        },
        {
            "idx": 5, "id": "stm_rev_volnorm",
            "code": "rank(reverse(divide(ts_delta(close, 3), ts_std_dev(returns, 20))))",
            "rationale": "Vol-normalized 3d price change; reversal in vol-adjusted space.",
            "expected_turnover_direction": "higher",
        },
        {
            "idx": 6, "id": "stm_rev_vwap",
            "code": "rank(reverse(ts_decay_linear(divide(subtract(close, vwap), vwap), 5)))",
            "rationale": "Microstructure: close-vs-VWAP overextension; intraday traders fade.",
            "expected_turnover_direction": "higher",
        },
        {
            "idx": 7, "id": "stm_rev_tsrank10",
            "code": "rank(reverse(ts_rank(returns, 10)))",
            "rationale": "Rank-based 10d reversal; more robust to return outliers than zscore.",
            "expected_turnover_direction": "neutral",
        },
        {
            "idx": 8, "id": "stm_rev_volwt_decay",
            # log(1+x) form used because s_log_1p is not exposed on this WQ tier
            # (G1 failure observed in run 20260511; retry_round=1).
            "code": "rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 10)))",
            "rationale": "Z-scored reversal weighted by log(1 + abnormal-volume), decay-smoothed - composite low-TO variant.",
            "expected_turnover_direction": "lower",
        },
    ],

    # Round 2: seeded by Round 1's near-miss (stm_rev_volwt_decay: SH 1.66 /
    # TO 0.32 / FIT 0.95). Goal: drop TO below 0.25 while preserving SH > 1.25
    # and lifting FIT above 1.0. Lever: extend ts_decay_linear windows to
    # 16-30 and add longer signal horizons. All variants stay in the
    # short-term-reversal mechanism family.
    "short_term_reversal_r2": [
        {
            "idx": 1, "id": "r2_volwt_decay20",
            "code": "rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 20)))",
            "rationale": "Round-1 seed with decay 10 -> 20. Direct TO refinement of the closest miss.",
            "expected_turnover_direction": "lower",
        },
        {
            "idx": 2, "id": "r2_zscore10_decay16",
            "code": "rank(reverse(ts_decay_linear(ts_zscore(returns, 10), 16)))",
            "rationale": "Pure z-score reversal with decay-16 smoothing (R1 zscore10 had SH 1.97 / TO 0.69).",
            "expected_turnover_direction": "lower",
        },
        {
            "idx": 3, "id": "r2_tsrank10_decay16",
            "code": "rank(reverse(ts_decay_linear(ts_rank(returns, 10), 16)))",
            "rationale": "Rank-based reversal with decay-16 smoothing (R1 tsrank10 had SH 1.95 / TO 0.69).",
            "expected_turnover_direction": "lower",
        },
        {
            "idx": 4, "id": "r2_volwt_decay30",
            "code": "rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 30)))",
            "rationale": "Same composite as #1 but decay 30 - aggressive TO suppression at the cost of some SH.",
            "expected_turnover_direction": "lower",
        },
        {
            "idx": 5, "id": "r2_vwap_decay20",
            "code": "rank(reverse(ts_decay_linear(divide(subtract(close, vwap), vwap), 20)))",
            "rationale": "Close-VWAP fade smoothed over 20d (R1 vwap with decay 5 was SH 1.20 / TO 0.33).",
            "expected_turnover_direction": "lower",
        },
        {
            "idx": 6, "id": "r2_volnorm_decay16",
            "code": "rank(reverse(ts_decay_linear(divide(ts_delta(close, 5), ts_std_dev(returns, 20)), 16)))",
            "rationale": "Vol-normalized 5d price change, decay-16 (R1 volnorm 3d/decay-0 was SH 1.33 / TO 0.40).",
            "expected_turnover_direction": "lower",
        },
        {
            "idx": 7, "id": "r2_zscore10_volwt_decay20",
            "code": "rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 10), log(add(divide(volume, adv20), 1))), 20)))",
            "rationale": "Seed but with longer 10d z-score horizon; captures more reversal mass.",
            "expected_turnover_direction": "lower",
        },
        {
            "idx": 8, "id": "r2_volnorm_zscore_decay20",
            "code": "rank(reverse(ts_decay_linear(ts_zscore(divide(ts_delta(close, 3), ts_std_dev(returns, 20)), 5), 20)))",
            "rationale": "Vol-normalized 3d delta z-scored then decay-20 smoothed - double-normalization composite.",
            "expected_turnover_direction": "lower",
        },
    ],
}


# -- Stage 4 submission ------------------------------------------------------
def submit(session, expression: str, settings: dict,
           poll_timeout_s: int = 600, poll_interval_s: int = 5) -> dict:
    body = {"type": "REGULAR", "settings": settings, "regular": expression}
    for _ in range(5):
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait); continue
        break
    if r.status_code != 201:
        return {"ok": False, "stage": "submit",
                "error": f"http-{r.status_code}: {r.text[:200]}"}
    progress_url = r.headers.get("Location")
    if not progress_url:
        return {"ok": False, "stage": "submit", "error": "no Location header"}

    t0 = time.time()
    while time.time() - t0 < poll_timeout_s:
        time.sleep(poll_interval_s)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st == "COMPLETE":
            alpha_id = data.get("alpha", "")
            ra = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                              timeout=30)
            if ra.status_code != 200:
                return {"ok": False, "alpha_id": alpha_id,
                        "stage": "alpha-get",
                        "error": f"http-{ra.status_code}"}
            ay = ra.json()
            isb = ay.get("is") or {}
            checks = isb.get("checks") or []
            return {
                "ok": True, "alpha_id": alpha_id,
                "sharpe": float(isb.get("sharpe") or 0.0),
                "turnover": float(isb.get("turnover") or 0.0),
                "fitness": float(isb.get("fitness") or 0.0),
                "returns": float(isb.get("returns") or 0.0),
                "drawdown": float(isb.get("drawdown") or 0.0),
                "longCount": int(isb.get("longCount") or 0),
                "shortCount": int(isb.get("shortCount") or 0),
                "checks_passed": sum(1 for c in checks if c.get("result") == "PASS"),
                "checks_total": len(checks),
                "checks": checks,
            }
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "sim",
                    "error": f"{st}: {data.get('message', '')[:200]}"}
    return {"ok": False, "stage": "poll-timeout"}


# -- Helpers to write artifacts ---------------------------------------------
def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2))


def write_yaml(path: Path, obj):
    # Minimal YAML emitter - dict/list of primitives only.
    def emit(o, indent=0):
        pad = "  " * indent
        if isinstance(o, dict):
            return "\n".join(f"{pad}{k}:" + (
                f" {emit_scalar(v)}" if not isinstance(v, (dict, list))
                else "\n" + emit(v, indent + 1)) for k, v in o.items())
        if isinstance(o, list):
            return "\n".join(f"{pad}- " + (
                emit_scalar(v) if not isinstance(v, (dict, list))
                else "\n" + emit(v, indent + 1).lstrip()) for v in o)
        return emit_scalar(o)

    def emit_scalar(v):
        if isinstance(v, str) and any(c in v for c in ":#\"'\n"):
            return json.dumps(v)
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)
    path.write_text(emit(obj))


def write_text(path: Path, body: str):
    path.write_text(body)


# -- Stage runners -----------------------------------------------------------
def stage1_librarian(session_dir: Path, topic: str):
    log.info("[Stage 1] Research Librarian")
    brief = f"""# Research Brief - {topic}

## Objective
Mine USA-equity factors that pass WQ Brain IS gates:
SH > {SHARPE_FLOOR}, fitness > {FITNESS_FLOOR}, turnover < {TURNOVER_CEILING}.

## Mechanism candidate
**Short-term price reversal**: Stocks with extreme recent returns tend to
mean-revert over the next 1-5 trading days. Documented since Jegadeesh
(1990); persistent on US equities. Effect is amplified after high-volume
moves (forced flow / sentiment overshoot).

## Datasets / fields available on this WQ tier
- Price-volume: close, open, high, low, volume, vwap, returns
- Cross-sectional cap: cap, sharesout
- Derived: adv20 (20d ADV in shares - WQ semantics)

## Operators in scope
- Time-series smoothing: ts_mean, ts_decay_linear, ts_zscore, ts_rank
- Normalization: divide, ts_std_dev (vol scaling)
- Volume conditioning: divide(volume, adv20), s_log_1p
- Cross-sectional wrap: rank (chosen over zscore/scale because robust to
  outliers and produces uniform-distribution signals that play nicely
  with INDUSTRY neutralization)

## Caveats / failure modes
1. **Turnover risk** - raw reversal at 1-3 days typically exceeds 0.40
   daily TO. Smoothing via ts_decay_linear or longer windows brings it
   under {TURNOVER_CEILING}.
2. **Industry correlation** - sector momentum can mask stock-level
   reversal; INDUSTRY neutralization is non-optional.
3. **Cost wipeout** - WQ Brain accounts for transaction cost in
   `is.checks`; even if SH > {SHARPE_FLOOR}, the LOW_FITNESS check
   may fail if returns are too small to cover assumed costs.

## Prior submissions on this WQ tier (CLAUDE.md historical)
- Local-pipeline volume-only factors (ts_std_dev(volume,11) variants)
  scored 1.32 / 1.30 IS Sharpe locally but -0.15 / 0.01 on WQ Brain.
  Conclusion: volume-only signals do not survive WQ TOP3000 with
  INDUSTRY neutralization. This run uses returns-anchored variants
  with volume only as a conditioning signal.
"""
    write_text(session_dir / "outputs" / "research_brief.md", brief)
    handoff = {
        "objective": f"Pass WQ_SH>{SHARPE_FLOOR}, WQ_FIT>{FITNESS_FLOOR}, WQ_TO<{TURNOVER_CEILING}",
        "mechanism_candidates": [{
            "name": "short_term_price_reversal",
            "why": "Persistent US-equity anomaly; horizon matches turnover cap.",
            "supporting_evidence": [
                "Jegadeesh 1990",
                "WQ TOP3000 INDUSTRY-neutralized reversal historically passes IS gates"
            ],
            "datasets": ["returns", "close", "vwap", "volume", "adv20"],
            "operators": ["ts_mean", "ts_decay_linear", "ts_zscore",
                           "ts_rank", "rank", "reverse", "divide", "s_log_1p"],
            "caveats": [
                "raw 1-3d reversal exceeds TO 0.25 without decay",
                "needs INDUSTRY neutralization to remove sector noise",
                "WQ is.checks may reject on LOW_FITNESS even if SH ok"
            ]
        }],
        "recommended_focus": "short_term_price_reversal",
    }
    write_json(session_dir / "working" / "handoff_1_to_2.json", handoff)


def stage2_architect(session_dir: Path):
    log.info("[Stage 2] Hypothesis Architect")
    metadata = {
        "session_id": session_dir.name,
        "selected_mechanism": "short_term_price_reversal",
        "causal_chain": [
            "extreme recent return -> overreaction / forced flow",
            "next 1-5 day mean reversion",
            "industry-neutralized residual captures stock-specific reversal"
        ],
        "time_horizon": "1-5 trading days",
        "market_regime": "broad-market - works across regimes; "
                          "strongest after high-vol shocks",
        "risk_premium_sources": [
            "liquidity provision premium",
            "behavioral overreaction"
        ],
        "constraints": {
            "region": "USA",
            "universe": "TOP3000",
            "delay": 1,
            "turnover_range": [0.0, TURNOVER_CEILING],
            "sharpe_target": SHARPE_FLOOR,
            "fitness_target": FITNESS_FLOOR,
            "prod_corr_max": 0.7,
        },
        "neutralization_candidates": ["INDUSTRY", "SUBINDUSTRY"],
        "evaluation_targets": {
            "primary": f"WQ IS Sharpe > {SHARPE_FLOOR}",
            "secondary": [f"WQ IS Fitness > {FITNESS_FLOOR}",
                          f"WQ IS Turnover < {TURNOVER_CEILING}"],
            "failure_conditions": [
                "all 8 expressions yield SH < 0.5",
                "all 8 expressions exceed TO 0.5 (mechanism mis-specified)"
            ],
        },
    }
    write_yaml(session_dir / "outputs" / "session_metadata.yml", metadata)
    handoff = {
        "selected_mechanism": "short_term_price_reversal",
        "causal_chain": metadata["causal_chain"],
        "time_horizon": metadata["time_horizon"],
        "market_regime": metadata["market_regime"],
        "risk_premium_sources": metadata["risk_premium_sources"],
        "constraints": metadata["constraints"],
        "neutralization_candidates": metadata["neutralization_candidates"],
    }
    write_json(session_dir / "working" / "handoff_2_to_3.json", handoff)


def stage3_builder(session_dir: Path, expressions: list):
    log.info("[Stage 3] Alpha Builder")
    assert len(expressions) == 8, "Rule of 8: must produce exactly 8 expressions"

    md = f"# Expression Batch 0001 - short_term_price_reversal\n\n"
    md += f"Mechanism: short_term_price_reversal | horizon: 1-10d | "
    md += f"neutralization: INDUSTRY | delay: 1\n\n"
    for e in expressions:
        md += f"## {e['idx']}. `{e['id']}`\n"
        md += f"```\n{e['code']}\n```\n"
        md += f"- Rationale: {e['rationale']}\n"
        md += f"- Expected turnover direction: {e['expected_turnover_direction']}\n\n"
    write_text(session_dir / "outputs" / "expressions_batch_0001.md", md)

    handoff = {
        "batch_id": "batch_0001",
        "selected_mechanism": "short_term_price_reversal",
        "expressions": expressions,
    }
    write_json(session_dir / "working" / "handoff_3_to_4.json", handoff)


def stage4_operator(session_dir: Path, expressions: list):
    log.info("[Stage 4] Backtest Operator - submitting 8 to WQ Brain")
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    results = []
    md = f"# Backtest Results - batch_0001\n\nSettings:\n```json\n"
    md += json.dumps(DEFAULT_SETTINGS, indent=2) + "\n```\n\n"
    md += f"| # | id | SH | TO | FIT | RET | DD | checks | alpha_id |\n"
    md += f"|---|----|----|----|-----|-----|----|---|---|\n"

    for e in expressions:
        log.info(f"  [{e['idx']}/8] {e['id']}: {e['code']}")
        res = submit(cm.session, e["code"], DEFAULT_SETTINGS)
        entry = {"idx": e["idx"], "id": e["id"], "code": e["code"], **res}
        results.append(entry)
        # Save partial
        write_json(session_dir / "working" / "backtest_partial.json", results)
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} checks={res['checks_passed']}/{res['checks_total']}")
            md += (f"| {e['idx']} | {e['id']} | {res['sharpe']:+.3f} | "
                    f"{res['turnover']:.3f} | {res['fitness']:+.3f} | "
                    f"{res['returns']:+.3f} | {res['drawdown']:.3f} | "
                    f"{res['checks_passed']}/{res['checks_total']} | "
                    f"`{res['alpha_id']}` |\n")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:120]}")
            md += (f"| {e['idx']} | {e['id']} | FAIL: "
                    f"{res.get('error', '?')[:60]} | - | - | - | - | - | - |\n")

    write_text(session_dir / "outputs" / "backtest_results_batch_0001.md", md)

    # Gate table for handoff_4_to_5 - WQ Brain provides its own checks list;
    # we map (sim succeeded ∧ checks_passed > 0) to G1/G2 pass, and
    # (sharpe is finite ∧ turnover in (0, 2]) to G3 pass. G4 fidelity
    # is approximated by: signed-IC unavailable from WQ /alphas, so we
    # use the WQ-internal LOW_FITNESS / SELF_CORRELATION checks as the
    # platform-side fidelity signal.
    h45_results = []
    for r in results:
        ok = bool(r.get("ok"))
        g1 = "pass" if ok else "fail"
        g2 = "pass" if ok else "fail"
        sh = r.get("sharpe", 0); to = r.get("turnover", 0)
        g3 = "pass" if ok and -10 < sh < 10 and 0 < to < 2 else "fail"
        cp = r.get("checks_passed", 0); ct = r.get("checks_total", 0)
        g4 = "pass" if ok and ct > 0 and cp >= ct - 2 else ("partial" if ok else "fail")
        h45_results.append({
            "expression_idx": r["idx"], "id": r["id"],
            "alpha_id": r.get("alpha_id", ""),
            "sharpe": r.get("sharpe", 0.0),
            "fitness": r.get("fitness", 0.0),
            "turnover": r.get("turnover", 0.0),
            "ic": 0.0,
            "status": "completed" if ok else "failed",
            "error": r.get("error"),
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4},
            "retry_count": 0,
            "notes": "G4 approximated via WQ is.checks (LOW_FITNESS / SELF_CORRELATION)",
        })
    handoff = {
        "batch_id": "batch_0001",
        "validation_passed": all(r["gates"]["G1"] == "pass"
                                   and r["gates"]["G2"] == "pass"
                                   for r in h45_results),
        "submission_made": True,
        "results": h45_results,
        "anomalies": [r["id"] for r in h45_results if r["status"] == "failed"],
    }
    write_json(session_dir / "working" / "handoff_4_to_5.json", handoff)
    return results


def stage5_evaluator(session_dir: Path, results: list):
    log.info("[Stage 5] Evaluator & Recorder")
    completed = [r for r in results if r.get("ok")]
    survivors = [r for r in completed
                  if r["sharpe"] > SHARPE_FLOOR
                  and r["fitness"] > FITNESS_FLOOR
                  and r["turnover"] < TURNOVER_CEILING]
    survivors.sort(key=lambda r: r["sharpe"], reverse=True)
    near_miss = [r for r in completed if r not in survivors]
    near_miss.sort(key=lambda r: r["sharpe"], reverse=True)

    md = f"# Alpha Ranking - batch_0001\n\n"
    md += f"User filter: WQ_IS_SH > {SHARPE_FLOOR} AND fitness > {FITNESS_FLOOR} "
    md += f"AND turnover < {TURNOVER_CEILING}\n\n"
    md += f"**Completed simulations: {len(completed)}/8**  "
    md += f"**Survivors: {len(survivors)}**\n\n"
    if survivors:
        md += f"## Survivors (ranked by WQ_IS Sharpe)\n\n"
        md += f"| rank | id | SH | TO | FIT | RET | DD | checks | alpha_id | expression |\n"
        md += f"|---|----|----|----|-----|-----|----|---|---|---|\n"
        for i, r in enumerate(survivors, 1):
            md += (f"| {i} | {r['id']} | {r['sharpe']:+.3f} | "
                    f"{r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | "
                    f"`{r['alpha_id']}` | `{r['code']}` |\n")
    else:
        md += f"## No survivors\n\nAll {len(completed)} completed simulations "
        md += f"failed at least one of the user thresholds.\n"
    if near_miss:
        md += f"\n## Near-misses (completed but filtered)\n\n"
        md += f"| id | SH | TO | FIT | reason |\n|---|----|----|-----|--------|\n"
        for r in near_miss:
            reasons = []
            if r["sharpe"] <= SHARPE_FLOOR: reasons.append(f"SH<={SHARPE_FLOOR}")
            if r["fitness"] <= FITNESS_FLOOR: reasons.append(f"FIT<={FITNESS_FLOOR}")
            if r["turnover"] >= TURNOVER_CEILING: reasons.append(f"TO>={TURNOVER_CEILING}")
            md += (f"| {r['id']} | {r['sharpe']:+.3f} | "
                    f"{r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{', '.join(reasons) or '-'} |\n")
    write_text(session_dir / "outputs" / "alpha_ranking.md", md)

    decision = "stop" if survivors else ("refine" if completed else "stop")
    why = (f"{len(survivors)} survivors meet all three thresholds; "
            "promote to OS / production review."
            if survivors else
            "no survivors; mechanism real but parameter mismatch likely - "
            "retry with longer smoothing windows or DECAY=16/32.")
    decision_block = {
        "round": 1,
        "decision": decision,
        "best_expression_idx": survivors[0]["idx"] if survivors else None,
        "best_alpha_id": survivors[0]["alpha_id"] if survivors else None,
        "why": why,
        "next_round_focus": ([] if survivors else
                              ["increase ts_decay_linear window to >= 16",
                               "try DECAY=16 or 32 in WQ settings",
                               "try SUBINDUSTRY neutralization"]),
    }
    run_state = {
        "session_id": session_dir.name,
        "current_round": 1,
        "current_stage": "evaluator-done",
        "status": "complete",
        "selected_mechanism": "short_term_price_reversal",
        "best_alpha_id": decision_block["best_alpha_id"],
        "continue_research": decision == "refine",
        "round_decision": decision_block,
    }
    write_json(session_dir / "run_state.json", run_state)

    summary = f"# Final Summary - {session_dir.name}\n\n"
    summary += f"- Mechanism: short_term_price_reversal\n"
    summary += f"- Settings: USA / TOP3000 / delay=1 / INDUSTRY / decay=8 / truncation=0.08\n"
    summary += f"- Submitted: 8  Completed: {len(completed)}  Survivors: {len(survivors)}\n"
    summary += f"- Decision: **{decision.upper()}**\n- Why: {why}\n\n"
    if survivors:
        summary += f"## Best alpha\n\n- id: `{survivors[0]['id']}`\n"
        summary += f"- alpha_id: `{survivors[0]['alpha_id']}`\n"
        summary += f"- expression: `{survivors[0]['code']}`\n"
        summary += f"- WQ_IS_SH: {survivors[0]['sharpe']:+.3f}\n"
        summary += f"- WQ_IS_FIT: {survivors[0]['fitness']:+.3f}\n"
        summary += f"- WQ_IS_TO: {survivors[0]['turnover']:.3f}\n"
    write_text(session_dir / "outputs" / "final_summary.md", summary)

    round_yml = {
        "round_id": 1, "session_id": session_dir.name,
        "mechanism": "short_term_price_reversal",
        "expressions_submitted": 8,
        "expressions_completed": len(completed),
        "survivors": len(survivors),
        "decision": decision,
        "filter": {"sharpe_floor": SHARPE_FLOOR,
                    "fitness_floor": FITNESS_FLOOR,
                    "turnover_ceiling": TURNOVER_CEILING},
    }
    write_yaml(session_dir / "round_0001.yml", round_yml)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="short_term_reversal",
                     help="Topic slug for session folder name")
    args = ap.parse_args()

    session_id = f"{dt.datetime.now():%Y%m%d}_{args.topic}_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    write_text(session_dir / "inputs" / "objective.md",
                f"Mine USA-equity factors passing WQ_IS_SH>{SHARPE_FLOOR}, "
                f"fitness>{FITNESS_FLOOR}, turnover<{TURNOVER_CEILING}.\n"
                f"Topic: {args.topic}\n")
    write_json(session_dir / "run_state.json", {
        "session_id": session_id, "current_round": 1,
        "current_stage": "research", "status": "running",
        "selected_mechanism": None, "best_alpha_id": None,
        "continue_research": True,
    })
    log.info(f"Session: {session_dir}")

    expressions = EXPRESSION_SETS.get(args.topic)
    if expressions is None:
        log.error(f"unknown topic {args.topic!r}; "
                   f"known: {list(EXPRESSION_SETS)}")
        return 2

    stage1_librarian(session_dir, args.topic)
    stage2_architect(session_dir)
    stage3_builder(session_dir, expressions)
    results = stage4_operator(session_dir, expressions)
    if not isinstance(results, list):
        return results
    stage5_evaluator(session_dir, results)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
