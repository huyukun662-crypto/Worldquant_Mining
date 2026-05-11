"""Round 8e: vol-weighted intraday reversal -- push family I across the bar.

R8d established intraday-return reversal is real but its raw TO/SH
frontier just misses (SH=1.45@TO=0.33 / SH=1.25@TO=0.17). The
reversal family lifted its raw signal by multiplying with abnormal-
volume weight log(volume/adv20+1). R8e applies the same trick to
the intraday signal:

  Family I (vol-weighted intraday reversal):
    M15  D=10, log(volume/adv20+1) weight
    M16  D=15, log(volume/adv20+1) weight (mid)
    M17  D=20, log(volume/adv20+1) weight (lower TO)
    M18  D=10, SUBINDUSTRY neut (finer residualizer)

Expression core (M15-M17, M18):
  reverse(ts_decay_linear(multiply((close-open)/open,
          log(volume/adv20+1)), D))
wrapped in zscore(), same proven settings (INDUSTRY for M15-M17,
SUBINDUSTRY for M18; decay=8, trunc=0.08, TOP3000, delay=1).

Filter: SH>1.3, FIT>1.0, TO<0.2.
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
log = logging.getLogger("r8e")

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
VOLWEIGHT = "log(add(divide(volume, adv20), 1))"


def expr_volwt(D: int) -> str:
    return (f"zscore(reverse(ts_decay_linear(multiply("
            f"{INTRADAY}, {VOLWEIGHT}), {D})))")


VARIANTS = [
    {
        "label": "M15_volwt_D10_IND",
        "family": "I_intraday_volwt",
        "expression": expr_volwt(10),
        "neutralization": "INDUSTRY",
        "notes": "intraday return * log(vol/adv20+1), 10d decay, INDUSTRY",
    },
    {
        "label": "M16_volwt_D15_IND",
        "family": "I_intraday_volwt",
        "expression": expr_volwt(15),
        "neutralization": "INDUSTRY",
        "notes": "intraday * vol weight, 15d decay (mid -- sweet spot probe)",
    },
    {
        "label": "M17_volwt_D20_IND",
        "family": "I_intraday_volwt",
        "expression": expr_volwt(20),
        "neutralization": "INDUSTRY",
        "notes": "intraday * vol weight, 20d decay (lower TO)",
    },
    {
        "label": "M18_volwt_D10_SUBIN",
        "family": "I_intraday_volwt",
        "expression": expr_volwt(10),
        "neutralization": "SUBINDUSTRY",
        "notes": "intraday * vol weight, 10d decay, SUBINDUSTRY (finer residualizer)",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_diversification_r8e_volwt_intraday_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Vol-weighted intraday reversal: push family I across the bar.\n"
        f"3 decays x INDUSTRY + 1 SUBINDUSTRY variant.\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        settings = dict(BASE)
        settings["neutralization"] = v["neutralization"]
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  [{v['family']}]")
        log.info(f"      {v['notes']}")
        log.info(f"      expr: {v['expression']}")
        res = r5.submit(cm.session, v["expression"], settings)
        entry = {
            "variant": v["label"],
            "family": v["family"],
            "neutralization": v["neutralization"],
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

    md = f"# Round 8e - vol-weighted intraday reversal\n\n"
    md += f"Settings: zscore wrapper, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Results\n\n"
    md += f"| variant | neut | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['neutralization']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['neutralization']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "volwt_intraday_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 8e final - vol-weighted intraday reversal\n\n"
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
                         f"- expression: `{r['expression']}`\n"
                         f"- neutralization: {r['neutralization']}\n"
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
