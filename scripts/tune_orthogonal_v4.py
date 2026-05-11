"""Round 8d: intraday-return reversal as the third distinct family.

Three short-horizon return-reversal flavors exist on US equity:
  (a) close-to-close return:   the original reversal family (R5-R7)
  (b) overnight gap (open - prev close): tested R8/N2, too weak
  (c) intraday return (close - open):     UNTESTED

Mechanism (c) is the day-trader rebalancing signal: stocks that closed
up during the day (positive close-open) tend to give back. It's
mechanically distinct from (a) because it isolates the intraday
component (vs the multi-day reversal driven by close-to-close
returns) and from (b) because it captures session activity rather
than overnight news/positioning.

Variants (4 sims):

  Family I (intraday return reversal):
    M11_intraday_D5     close-open / open, REVERSED, 5d decay
    M12_intraday_D10    same, 10d decay
    M13_intraday_D20    same, 20d decay

  Family L (adv20-LEVEL alternative -- different flavor of liqflow):
    M14_advratio_D20    adv20 / ts_mean(adv20, 60), REVERSED
                        (level signal, not delta)

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1). Filter (lowered): SH>1.3, FIT>1.0, TO<0.2.

If family I yields >=1 survivor, we have 3 distinct mechanism families
total (reversal + liqflow + intraday).
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
log = logging.getLogger("r8d")

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

INTRADAY = "divide(subtract(close, open), open)"

VARIANTS = [
    {
        "label": "M11_intraday_D5",
        "family": "I_intraday_reversal",
        "expression": f"zscore(reverse(ts_decay_linear({INTRADAY}, 5)))",
        "notes": "(close-open)/open REVERSED, 5d decay (short)",
    },
    {
        "label": "M12_intraday_D10",
        "family": "I_intraday_reversal",
        "expression": f"zscore(reverse(ts_decay_linear({INTRADAY}, 10)))",
        "notes": "(close-open)/open REVERSED, 10d decay (mid)",
    },
    {
        "label": "M13_intraday_D20",
        "family": "I_intraday_reversal",
        "expression": f"zscore(reverse(ts_decay_linear({INTRADAY}, 20)))",
        "notes": "(close-open)/open REVERSED, 20d decay (long, lower TO)",
    },
    {
        "label": "M14_advratio_D20",
        "family": "L_liquidity_flow",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "divide(adv20, ts_mean(adv20, 60)), 20)))"
        ),
        "notes": "adv20 / 60d-mean(adv20), REVERSED -- liquidity LEVEL alt to M1's delta",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_diversification_r8d_intraday_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Target intraday-return reversal as the THIRD distinct mechanism family.\n"
        f"3 intraday variants + 1 adv20-level liquidity alternative.\n"
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

    md = f"# Round 8d - intraday-return reversal\n\n"
    md += f"3 intraday variants + 1 adv20-level alt.\n"
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
    (session_dir / "outputs" / "intraday_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 8d final - intraday-return reversal\n\n"
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
