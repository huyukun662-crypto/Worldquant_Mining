"""Round 7: drive TO < 0.15 while holding SH > 1.35 and FIT > 1.0.

New user filter (raised bar):
  SH > 1.35  AND  FIT > 1.0  AND  TO < 0.15

Current best-by-TO survivor (KPnlWb9j / R6/V9) has TO=0.183 with
outer ts_decay_linear window=30. To get under 0.15 we need MORE
smoothing. Empirically: window 20 -> 30 cut TO from 0.225 -> 0.183
(~18% drop), with SH cost ~0.10.  Extending to 40-60 should drop
TO under 0.15; the question is whether SH holds above 1.35.

Settings fixed at the proven combo:
  wrapper=zscore, neut=INDUSTRY, truncation=0.08, universe=TOP3000,
  delay=1, pasteurization=ON.

WQ-side decay defaults to 8 (the optimal from Rounds 3-6). One
variant probes higher WQ-decay as an alternate path.

5 variants:
  V11  zwin=3 outer=40 wqdecay=8   (V6 champion + more smoothing)
  V12  zwin=3 outer=50 wqdecay=8   (V6 + a lot more smoothing)
  V13  zwin=5 outer=40 wqdecay=8   (V1/V9 extension)
  V14  zwin=5 outer=60 wqdecay=8   (V1 + much more -- find SH floor)
  V15  zwin=3 outer=30 wqdecay=12  (alternate lever: WQ-side decay)
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
log = logging.getLogger("r7")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.35
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.15

BASE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
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


def expr(zwin: int, outer: int) -> str:
    return (f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_zscore(returns, {zwin}), {LIQ}), {outer})))")


VARIANTS = [
    {"label": "V11_zwin3_D40_wqd8",  "zwin": 3, "outer": 40, "wq_decay": 8},
    {"label": "V12_zwin3_D50_wqd8",  "zwin": 3, "outer": 50, "wq_decay": 8},
    {"label": "V13_zwin5_D40_wqd8",  "zwin": 5, "outer": 40, "wq_decay": 8},
    {"label": "V14_zwin5_D60_wqd8",  "zwin": 5, "outer": 60, "wq_decay": 8},
    {"label": "V15_zwin3_D30_wqd12", "zwin": 3, "outer": 30, "wq_decay": 12},
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

    session_id = f"{dt.datetime.now():%Y%m%d}_short_term_reversal_r7_low_turnover_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Drive TO under 0.15 while holding SH>1.35 and FIT>1.0.\n"
        f"Settings: zscore wrapper, INDUSTRY, trunc=0.08, TOP3000.\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        expression = expr(v["zwin"], v["outer"])
        settings = dict(BASE)
        settings["decay"] = v["wq_decay"]
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: "
                 f"zwin={v['zwin']} outer_decay={v['outer']} "
                 f"wq_decay={v['wq_decay']}")
        log.info(f"      expr: {expression}")
        res = r5.submit(cm.session, expression, settings)
        entry = {
            "variant": v["label"],
            "zwin": v["zwin"], "outer": v["outer"], "wq_decay": v["wq_decay"],
            "expression": expression,
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

    md = f"# Round 7 - low-turnover sweep (raised bar)\n\n"
    md += f"All variants: zscore wrapper, INDUSTRY, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Reference points\n\n"
    md += f"- R6/V6 `QPnZ8l6p` (zwin=3, D=20, wqd=8): SH=+1.870 TO=0.207\n"
    md += f"- R6/V9 `KPnlWb9j` (zwin=5, D=30, wqd=8): SH=+1.620 TO=0.183\n"
    md += f"- R5/V1 `RRNj5MVb` (zwin=5, D=20, wqd=8): SH=+1.720 TO=0.225\n\n"
    md += f"## This round\n\n"
    md += f"| variant | zwin | outer | wq_decay | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['zwin']} | {r['outer']} | {r['wq_decay']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['zwin']} | {r['outer']} | {r['wq_decay']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "low_turnover_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 7 final - low-turnover sweep\n\n"
                f"Variants: {len(results)} (extend outer ts_decay_linear)\n"
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
                         f"- SH={r['sharpe']:+.3f}  TO={r['turnover']:.3f}  "
                         f"FIT={r['fitness']:+.3f}  RET={r['returns']:+.3f}  "
                         f"DD={r['drawdown']:.3f}\n"
                         f"- checks: {r['checks_passed']}/{r['checks_total']}\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(summary)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
