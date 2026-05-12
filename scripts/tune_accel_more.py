"""Round 16: 3 more NEW SH>=2 alpha_ids in price-acceleration family.

Budget: R12 gave 2 (D=30, D=50). R15 gave 2 more (W=2/D=40, W=3/D=40).
Total NEW so far = 2. Need 3 more to hit the user's 5-target.

5 sims at high-probability points based on R12+R15 evidence base:

  H1  accel(W=1) D=20  -- shorter decay, baseline R12 inner signal
  H2  accel(W=1) D=25  -- another decay between W1 and prior
  H3  accel(W=2) D=30  -- W=2 inner with R12/W1's decay
  H4  accel(W=2) D=50  -- W=2 inner with R12/W2's decay
  H5  accel(W=3) D=60  -- W=3 inner with longer decay

R12 SH at fixed W=1 across decays: D=30->2.05, D=50->2.03, D=80->1.95.
R15 SH at fixed D=40 across W: W=2->2.10, W=3->2.11, W=5->1.99.
Predicting >=4 of these to clear SH>=2.

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1, pasteurization=ON, nanHandling=OFF).

Filter: SH>=2.0, FIT>1.0, TO<0.25.
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
log = logging.getLogger("r16")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 2.0
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

VOLWEIGHT = "log(add(divide(volume, adv20), 1))"


def expr(W: int, D: int) -> str:
    accel = f"subtract(returns, ts_delay(returns, {W}))"
    return f"zscore(reverse(ts_decay_linear(multiply({accel}, {VOLWEIGHT}), {D})))"


VARIANTS = [
    {"label": "H1_accel1_D20", "W": 1, "D": 20},
    {"label": "H2_accel1_D25", "W": 1, "D": 25},
    {"label": "H3_accel2_D30", "W": 2, "D": 30},
    {"label": "H4_accel2_D50", "W": 2, "D": 50},
    {"label": "H5_accel3_D60", "W": 3, "D": 60},
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r16_accel_more_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"3+ more NEW alpha_ids targeting SH>=2 TO<0.25 to fill 5-target.\n"
        f"Filter: SH>={SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        expression = expr(v["W"], v["D"])
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  W={v['W']} D={v['D']}")
        log.info(f"      expr: {expression}")
        try:
            res = r5.submit(cm.session, expression, BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "W": v["W"], "D": v["D"],
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
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = f"# Round 16 - more NEW SH>=2 alphas in price-accel family\n\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH >= {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Results\n\n"
    md += f"| variant | W | D | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---:|---:|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] >= SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['W']} | {r['D']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['W']} | {r['D']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "accel_more_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 16 final - more NEW SH>=2 alphas\n\n"
                f"Variants: {len(results)}\n"
                f"Filter: SH>={SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, "
                f"TO<{TURNOVER_CEILING}\n"
                f"Survivors: {len(survivors)}/{len(results)}\n")
    if survivors:
        survivors.sort(key=lambda r: r["sharpe"], reverse=True)
        summary += "\n## Survivors (ranked by SH)\n\n"
        for r in survivors:
            summary += (f"### {r['variant']}\n"
                         f"- alpha_id: `{r['alpha_id']}`\n"
                         f"- W={r['W']} D={r['D']}\n"
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
