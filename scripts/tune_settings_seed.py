"""Round 3: settings sweep on the best round-2 seed.

Round 2's r2_volwt_decay20 passed SH and TO but was capped at FIT=0.96.
Hypothesis: the FIT ceiling is driven by simulation settings (truncation
caps the long/short concentration, and WQ-side decay=8 double-smooths
on top of the expression-level ts_decay_linear). This round fixes the
expression and sweeps settings.

Variants (5 sims, ~10-15 min):

    A: truncation=0.08, decay=0, INDUSTRY   -- drop WQ-side decay only
    B: truncation=0.05, decay=0, INDUSTRY   -- mild concentration
    C: truncation=0.03, decay=0, INDUSTRY   -- aggressive concentration
    D: truncation=0.05, decay=0, SUBINDUSTRY -- finer neutralization
    E: truncation=0.03, decay=0, SUBINDUSTRY -- aggressive both

Same expression / universe / region. Baseline for comparison is
round 2's sim 1: SH 1.51 / TO 0.219 / FIT 0.960 with truncation=0.08,
decay=8, INDUSTRY.

Filter at the end: SH > 1.25 AND FIT > 1.0 AND TO < 0.25 on
WQ-Brain-returned metrics (authoritative per CLAUDE.md).
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
log = logging.getLogger("r3")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.25
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.25

SEED_ID = "r2_volwt_decay20"
SEED_EXPRESSION = ("rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), "
                    "log(add(divide(volume, adv20), 1))), 20)))")

BASE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VARIANTS = [
    {"label": "A_trunc08_decay0_IND",   "truncation": 0.08, "decay": 0, "neutralization": "INDUSTRY"},
    {"label": "B_trunc05_decay0_IND",   "truncation": 0.05, "decay": 0, "neutralization": "INDUSTRY"},
    {"label": "C_trunc03_decay0_IND",   "truncation": 0.03, "decay": 0, "neutralization": "INDUSTRY"},
    {"label": "D_trunc05_decay0_SUBIN", "truncation": 0.05, "decay": 0, "neutralization": "SUBINDUSTRY"},
    {"label": "E_trunc03_decay0_SUBIN", "truncation": 0.03, "decay": 0, "neutralization": "SUBINDUSTRY"},
]


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    # Import submit() from the 5-agent runner
    r5 = _load(REPO / "scripts" / "run_5agent_workflow.py", "r5")

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    log.info(f"seed: {SEED_ID} = {SEED_EXPRESSION}")

    session_id = f"{dt.datetime.now():%Y%m%d}_short_term_reversal_r3_settings_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Settings sweep on seed {SEED_ID}.\n"
        f"Expression: {SEED_EXPRESSION}\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        settings = dict(BASE)
        settings["truncation"] = v["truncation"]
        settings["decay"] = v["decay"]
        settings["neutralization"] = v["neutralization"]
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: trunc={v['truncation']} "
                 f"decay={v['decay']} neut={v['neutralization']}")
        res = r5.submit(cm.session, SEED_EXPRESSION, settings)
        entry = {"variant": v["label"], "settings": v, **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} checks={res['checks_passed']}/{res['checks_total']}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:120]}")

    # Render results markdown + ranking
    md = f"# Round 3 - Settings sweep on `{SEED_ID}`\n\n"
    md += f"Expression: `{SEED_EXPRESSION}`\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Round-2 baseline (for reference)\n\n"
    md += f"trunc=0.08, decay=8, INDUSTRY  -> SH=1.510 TO=0.219 FIT=0.960  (FIT only)\n\n"
    md += f"## This round\n\n"
    md += f"| variant | trunc | decay | neut | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---|---|---|---|---|---|---|---|---|\n"
    survivors = []
    for r in results:
        v = r["settings"]
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {v['truncation']} | {v['decay']} | "
                    f"{v['neutralization']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                    f"{r['fitness']:+.3f} | {r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {v['truncation']} | {v['decay']} | "
                    f"{v['neutralization']} | FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"

    (session_dir / "outputs" / "settings_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    # Final summary
    summary = (f"# Round 3 final - settings sweep\n\n"
                f"- Seed: `{SEED_ID}`\n"
                f"- Variants: {len(results)} (settings only; expression fixed)\n"
                f"- Survivors under SH>{SHARPE_FLOOR}/FIT>{FITNESS_FLOOR}/"
                f"TO<{TURNOVER_CEILING}: {len(survivors)}\n")
    if survivors:
        b = max(survivors, key=lambda r: r["sharpe"])
        summary += (f"\n## Best alpha\n- variant: {b['variant']}\n"
                     f"- alpha_id: `{b['alpha_id']}`\n"
                     f"- SH={b['sharpe']:+.3f}  TO={b['turnover']:.3f}  "
                     f"FIT={b['fitness']:+.3f}  RET={b['returns']:+.3f}\n")
    (session_dir / "outputs" / "final_summary.md").write_text(summary)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
