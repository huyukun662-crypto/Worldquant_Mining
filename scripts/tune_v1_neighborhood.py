"""Round 6: V1-neighborhood sweep to mine more deliverables.

Round 5 produced 3 survivors; V1 was best:
  zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5),
         log(add(divide(volume, adv20), 1))), 20)))
  -> SH=+1.720  TO=0.225  FIT=+1.320  (alpha_id RRNj5MVb)

Settings fixed at the proven combo:
  wrapper=zscore, neutralization=INDUSTRY, decay=8, truncation=0.08,
  universe=TOP3000, delay=1, pasteurization=ON.

This round perturbs the expression around V1 in 5 orthogonal directions
to surface correlated-but-distinct alphas:

  V6  shorter inner reversal:    ts_zscore(returns, 3)  (was 5)
  V7  longer inner reversal:     ts_zscore(returns, 10) (was 5)
  V8  shorter outer decay:       ts_decay_linear(..., 15)  (was 20)
  V9  longer outer decay:        ts_decay_linear(..., 30)  (was 20)
  V10 alt liquidity weight:      ts_zscore(volume, 20)  replaces log(volume/adv20+1)

Filter: SH > 1.25 AND FIT > 1.0 AND TO < 0.25.
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
log = logging.getLogger("r6")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.25
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.25

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

LIQ = "log(add(divide(volume, adv20), 1))"

VARIANTS = [
    {
        "label": "V6_zwin3",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_zscore(returns, 3), {LIQ}), 20)))"
        ),
        "perturb": "ts_zscore window: 5 -> 3 (shorter reversal)",
    },
    {
        "label": "V7_zwin10",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_zscore(returns, 10), {LIQ}), 20)))"
        ),
        "perturb": "ts_zscore window: 5 -> 10 (longer reversal)",
    },
    {
        "label": "V8_decay15",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_zscore(returns, 5), {LIQ}), 15)))"
        ),
        "perturb": "outer decay: 20 -> 15 (less smoothing)",
    },
    {
        "label": "V9_decay30",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_zscore(returns, 5), {LIQ}), 30)))"
        ),
        "perturb": "outer decay: 20 -> 30 (more smoothing)",
    },
    {
        "label": "V10_volz",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_zscore(returns, 5), ts_zscore(volume, 20)), 20)))"
        ),
        "perturb": "liquidity weight: log(vol/adv20+1) -> ts_zscore(volume, 20)",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_short_term_reversal_r6_v1_neighborhood_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"V1-neighborhood sweep to surface more deliverables.\n"
        f"Settings fixed: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000.\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: {v['perturb']}")
        log.info(f"      expr: {v['expression']}")
        res = r5.submit(cm.session, v["expression"], BASE)
        entry = {
            "variant": v["label"],
            "perturb": v["perturb"],
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
            log.warning(f"      FAIL: {res.get('error', '?')[:120]}")

    md = f"# Round 6 - V1 neighborhood sweep\n\n"
    md += f"All variants use: zscore wrapper, INDUSTRY neutralization, "
    md += f"decay=8, truncation=0.08, USA/TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## V1 baseline (from Round 5)\n\n"
    md += f"`RRNj5MVb`: SH=+1.720  TO=0.225  FIT=+1.320  RET=+0.132  checks=7/8\n\n"
    md += f"## This round\n\n"
    md += f"| variant | perturbation | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---|---|---|---|---|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['perturb']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['perturb']} | FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "v1_neighborhood_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 6 final - V1 neighborhood\n\n"
                f"Variants: {len(results)} (expression perturbations around V1)\n"
                f"Survivors under SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, "
                f"TO<{TURNOVER_CEILING}: {len(survivors)}\n")
    if survivors:
        survivors.sort(key=lambda r: r["sharpe"], reverse=True)
        summary += "\n## All survivors (ranked by SH)\n\n"
        for r in survivors:
            summary += (f"### {r['variant']}\n"
                         f"- alpha_id: `{r['alpha_id']}`\n"
                         f"- expression: `{r['expression']}`\n"
                         f"- perturbation: {r['perturb']}\n"
                         f"- SH={r['sharpe']:+.3f}  TO={r['turnover']:.3f}  "
                         f"FIT={r['fitness']:+.3f}  RET={r['returns']:+.3f}  "
                         f"DD={r['drawdown']:.3f}\n"
                         f"- checks: {r['checks_passed']}/{r['checks_total']}\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(summary)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
