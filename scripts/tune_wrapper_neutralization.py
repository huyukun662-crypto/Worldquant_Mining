"""Round 5: wrapper x neutralization sweep on the SH+TO-passing seed.

Round 2 sim 1 (r2_volwt_decay20) and round 3 settings sweep proved:
- SH=1.51, TO=0.219, FIT=0.96 with default settings (rank wrapper, INDUSTRY, decay=8)
- FIT cap at ~0.98 across truncation {0.08, 0.05, 0.03}
- SUBINDUSTRY adds +5% SH, no FIT change
- WQ decay 8 -> 0 doubles SH but also TO (TO becomes >0.5)

Two settings NOT yet tested that directly affect returns magnitude:
1. Cross-sectional wrapper: rank flattens to uniform [0,1] -
   replacing with zscore or scale preserves magnitude information.
2. Neutralization: INDUSTRY filters out the industry-momentum carrier;
   MARKET only removes broad-market drift; NONE keeps everything.

Variants (5 sims, ~10-15 min):
  V1: zscore wrapper / INDUSTRY  / decay=8 / trunc=0.08
  V2: scale  wrapper / INDUSTRY  / decay=8 / trunc=0.08
  V3: rank   wrapper / MARKET    / decay=8 / trunc=0.08
  V4: rank   wrapper / NONE      / decay=8 / trunc=0.08
  V5: zscore wrapper / MARKET    / decay=8 / trunc=0.08

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
log = logging.getLogger("r5")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.25
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.25

CORE = ("reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), "
        "log(add(divide(volume, adv20), 1))), 20))")

BASE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 8,
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VARIANTS = [
    {"label": "V1_zscore_IND",     "wrapper": "zscore", "neutralization": "INDUSTRY"},
    {"label": "V2_scale_IND",      "wrapper": "scale",  "neutralization": "INDUSTRY"},
    {"label": "V3_rank_MARKET",    "wrapper": "rank",   "neutralization": "MARKET"},
    {"label": "V4_rank_NONE",      "wrapper": "rank",   "neutralization": "NONE"},
    {"label": "V5_zscore_MARKET",  "wrapper": "zscore", "neutralization": "MARKET"},
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

    session_id = f"{dt.datetime.now():%Y%m%d}_short_term_reversal_r5_wrapper_neut_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Wrapper x neutralization sweep on seed r2_volwt_decay20.\n"
        f"Core: {CORE}\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        expression = f"{v['wrapper']}({CORE})"
        settings = dict(BASE)
        settings["neutralization"] = v["neutralization"]
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: {expression}")
        log.info(f"      settings: neut={v['neutralization']} decay={settings['decay']} "
                 f"trunc={settings['truncation']} universe={settings['universe']}")
        res = r5.submit(cm.session, expression, settings)
        entry = {"variant": v["label"], "wrapper": v["wrapper"], "expression": expression,
                  "neutralization": v["neutralization"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} RET={res['returns']:+.3f} "
                     f"checks={res['checks_passed']}/{res['checks_total']}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:120]}")

    # Render markdown
    md = f"# Round 5 - wrapper x neutralization sweep\n\n"
    md += f"Core (under wrapper): `{CORE}`\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## R2 baseline (for reference)\n\n"
    md += f"`rank` wrapper / INDUSTRY -> SH=1.510 TO=0.219 FIT=0.960  (FIT only)\n\n"
    md += f"## This round\n\n"
    md += f"| variant | wrapper | neut | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---|---|---|---|---|---|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['wrapper']} | {r['neutralization']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['wrapper']} | {r['neutralization']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "wrapper_neut_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 5 final - wrapper x neutralization\n\n"
                f"Variants: {len(results)} (5 wrapper/neut combos, expression core fixed)\n"
                f"Survivors: {len(survivors)}/{len(results)}\n")
    if survivors:
        b = max(survivors, key=lambda r: r["sharpe"])
        summary += (f"\n## Best alpha (DELIVERABLE)\n"
                     f"- variant: {b['variant']}\n"
                     f"- alpha_id: `{b['alpha_id']}`\n"
                     f"- expression: `{b['expression']}`\n"
                     f"- settings: wrapper={b['wrapper']}, neutralization="
                     f"{b['neutralization']}, decay=8, truncation=0.08, "
                     f"universe=TOP3000, delay=1\n"
                     f"- SH={b['sharpe']:+.3f}  TO={b['turnover']:.3f}  "
                     f"FIT={b['fitness']:+.3f}  RET={b['returns']:+.3f}\n")
    (session_dir / "outputs" / "final_summary.md").write_text(summary)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
