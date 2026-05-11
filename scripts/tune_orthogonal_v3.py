"""Round 8c: realized-vol family + one liquidity-flow bridge.

Under the lowered user bar (SH>1.3, FIT>1.0, TO<0.2) we have:
  Reversal family (R5/R6/R7): 5 survivors  (one family)
  Liquidity-flow family (R8b/M1): 1 survivor  (second family)
We still need a THIRD distinct mechanism family. Volume-burst (R8b/M3)
and close-strength (R8b/M4) were too weak; overnight gap (R8/N2) was
too noisy. Realized-volatility (vol-of-returns) is mechanistically
distinct from all of the above -- it captures the VOL-RISK PREMIUM
rather than directional reversion.

Variants (5 sims):

  Family RV (realized-vol -- vol risk premium):
    M6_volrev_W20D20   -- 20d ts_std_dev(returns), REVERSED, 20d decay
    M7_volrev_W60D20   -- 60d ts_std_dev(returns), REVERSED, 20d decay
    M8_volrev_W20D30   -- 20d std_dev, REVERSED, 30d decay (lower TO)
    M9_volmom_W60D20   -- 60d std_dev, LONG (no reverse, alt direction)

  Family L bridge:
    M10_liqflip_w30D10 -- 30d delta in adv20 (between M1=20d and M2=60d)

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1, pasteurization=ON). Filter: SH>1.3, FIT>1.0, TO<0.2.

Goal: at least one survivor in family RV (third distinct mechanism).
M10 is insurance in case RV all fails.
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
log = logging.getLogger("r8c")

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
        "label": "M6_volrev_W20D20",
        "family": "RV_realized_vol",
        "expression": "zscore(reverse(ts_decay_linear(ts_std_dev(returns, 20), 20)))",
        "notes": "20d realized vol of returns, REVERSED (vol risk premium)",
    },
    {
        "label": "M7_volrev_W60D20",
        "family": "RV_realized_vol",
        "expression": "zscore(reverse(ts_decay_linear(ts_std_dev(returns, 60), 20)))",
        "notes": "60d realized vol of returns, REVERSED",
    },
    {
        "label": "M8_volrev_W20D30",
        "family": "RV_realized_vol",
        "expression": "zscore(reverse(ts_decay_linear(ts_std_dev(returns, 20), 30)))",
        "notes": "20d realized vol, REVERSED, 30d decay (lower TO)",
    },
    {
        "label": "M9_volmom_W60D20",
        "family": "RV_realized_vol",
        "expression": "zscore(ts_decay_linear(ts_std_dev(returns, 60), 20))",
        "notes": "60d realized vol, LONG (no reverse): high-vol = high-beta carrier",
    },
    {
        "label": "M10_liqflip_w30D10",
        "family": "L_liquidity_flow",
        "expression": (
            "zscore(reverse(ts_decay_linear(divide(subtract(adv20, "
            "ts_delay(adv20, 30)), ts_delay(adv20, 30)), 10)))"
        ),
        "notes": "30d delta in adv20, REVERSED (bridge between M1=20d and M2=60d)",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_diversification_r8c_realized_vol_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Target realized-vol family for the third distinct mechanism.\n"
        f"4 RV variants + 1 liquidity-flow bridge (insurance).\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  [{v['family']}]")
        log.info(f"      {v['notes']}")
        log.info(f"      expr: {v['expression']}")
        res = r5.submit(cm.session, v["expression"], BASE)
        entry = {
            "variant": v["label"],
            "family": v["family"],
            "notes": v["notes"],
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

    md = f"# Round 8c - realized-vol family\n\n"
    md += f"4 RV variants + 1 liquidity-flow bridge.\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Results\n\n"
    md += f"| variant | family | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['family']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['family']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"

    families_covered = sorted({r["family"] for r in survivors})
    md += f"\n**Distinct families covered: {len(families_covered)}** ({', '.join(families_covered) if families_covered else 'none'})\n"
    (session_dir / "outputs" / "realized_vol_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 8c final - realized-vol family\n\n"
                f"Variants: {len(results)}\n"
                f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, "
                f"TO<{TURNOVER_CEILING}\n"
                f"Survivors: {len(survivors)}/{len(results)}\n"
                f"Distinct families covered: {len(families_covered)}\n")
    if survivors:
        survivors.sort(key=lambda r: r["sharpe"], reverse=True)
        summary += "\n## Survivors (ranked by SH, grouped by family)\n\n"
        by_fam = {}
        for r in survivors:
            by_fam.setdefault(r["family"], []).append(r)
        for fam, rs in by_fam.items():
            summary += f"### Family: {fam}\n\n"
            for r in rs:
                summary += (f"#### {r['variant']}\n"
                             f"- alpha_id: `{r['alpha_id']}`\n"
                             f"- expression: `{r['expression']}`\n"
                             f"- notes: {r['notes']}\n"
                             f"- SH={r['sharpe']:+.3f}  TO={r['turnover']:.3f}  "
                             f"FIT={r['fitness']:+.3f}  RET={r['returns']:+.3f}  "
                             f"DD={r['drawdown']:.3f}\n"
                             f"- checks: {r['checks_passed']}/{r['checks_total']}\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(summary)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
