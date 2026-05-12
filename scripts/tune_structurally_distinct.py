"""Round 9: structurally and logically distinct alphas, no overlap.

Current 3 deliverables share a structural skeleton:
  zscore(reverse(ts_decay_linear(multiply(<signal>, <weight>), <D>)))

R9 targets 4 candidates with NEW operator structures and/or new
directions (no reverse), to find 3 alphas that don't overlap with:
  1. close-close reversal (6XR7Om3p)  -- ts_zscore(returns) * vol weight
  2. liquidity-flow short-attention (2rvMNKmP) -- adv20 delta REVERSED
  3. intraday vol-weighted (GrnPdaXQ) -- (close-open)/open * vol weight

  S1_corr_rev    -- ts_corr(returns, vol/adv20, 20), REVERSED
                    [new operator: ts_corr  | structure: smoothed-corr]
  S2_liqlong     -- relative volume LONG, NO REVERSE
                    [new direction: opposite of liqflow short-attention]
  S3_argmin      -- ts_arg_min(close, 60), REVERSED
                    [new operator: ts_arg_min | logic: distance-to-bottom]
  S4_corr_long   -- ts_corr(close, volume, 20), LONG NO REVERSE
                    [new operator AND new direction]

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1, pasteurization=ON). Filter: SH>1.3, FIT>1.0, TO<0.2.

NOTE: if ts_arg_min is blocked on this account tier (like ts_max was),
S3 fails with G1 -- accept and continue.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r9")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.3
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.2

BASE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 8,
    "truncation": 0.08,
    "neutralization": "INDUSTRY",
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VARIANTS = [
    {
        "label": "S1_corr_rev",
        "logic": "return-vol corr reversal",
        "structure": "ts_corr inside smoothed reverse",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "ts_corr(returns, divide(volume, adv20), 20), 10)))"
        ),
    },
    {
        "label": "S2_liqlong",
        "logic": "relative-volume LONG (sustained attention)",
        "structure": "no reverse, smoothed level signal",
        "expression": (
            "zscore(ts_decay_linear(divide(volume, adv20), 20))"
        ),
    },
    {
        "label": "S3_argmin_rev",
        "logic": "days-since-60d-low reversal",
        "structure": "ts_arg_min inside smoothed reverse (new operator)",
        "expression": (
            "zscore(reverse(ts_decay_linear(ts_arg_min(close, 60), 20)))"
        ),
    },
    {
        "label": "S4_corr_long",
        "logic": "close-volume corr continuation (attention)",
        "structure": "ts_corr inside smoothed NO reverse",
        "expression": (
            "zscore(ts_decay_linear(ts_corr(close, volume, 20), 10))"
        ),
    },
]


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    r5 = _load(REPO / "scripts" / "run_5agent_workflow.py", "r5")

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    session_id = f"{dt.datetime.now():%Y%m%d}_diversification_r9_corr_argmin_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"3 structurally-distinct alphas without overlap with the 3 deliverables.\n"
        f"Uses new operators (ts_corr, ts_arg_min) and/or new direction (no reverse).\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      logic:     {v['logic']}")
        log.info(f"      structure: {v['structure']}")
        log.info(f"      expr:      {v['expression']}")
        res = r5.submit(cm.session, v["expression"], BASE)
        entry = {
            "variant": v["label"],
            "logic": v["logic"],
            "structure": v["structure"],
            "expression": v["expression"],
            **res,
        }
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} RET={res['returns']:+.3f} "
                     f"checks={res['checks_passed']}/{res['checks_total']}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = f"# Round 9 - structurally distinct alphas (no overlap)\n\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Results\n\n"
    md += f"| variant | logic | structure | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['logic']} | {r['structure']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['logic']} | {r['structure']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "structurally_distinct_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 9 final - structurally distinct alphas\n\n"
                f"Variants: {len(results)}\n"
                f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, "
                f"TO<{TURNOVER_CEILING}\n"
                f"Survivors: {len(survivors)}/{len(results)}\n")
    if survivors:
        survivors.sort(key=lambda r: r["sharpe"], reverse=True)
        summary += "\n## Survivors (ranked by SH)\n\n"
        for r in survivors:
            summary += (f"### {r['variant']}\n"
                         f"- alpha_id: `{r['alpha_id']}`\n"
                         f"- logic: {r['logic']}\n"
                         f"- structure: {r['structure']}\n"
                         f"- expression: `{r['expression']}`\n"
                         f"- SH={r['sharpe']:+.3f}  TO={r['turnover']:.3f}  "
                         f"FIT={r['fitness']:+.3f}  RET={r['returns']:+.3f}  "
                         f"DD={r['drawdown']:.3f}\n"
                         f"- checks: {r['checks_passed']}/{r['checks_total']}\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(summary)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
