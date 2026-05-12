"""Round 29: 2+ more fresh alphas at SH>=1.75 TO<0.2 FIT>1.25.

R28 delivered 3 NEW (CC1 W=4 D=40, CC2 W=2 D=35, CC3 W=2 D=45).
R29 mines 4 more untested (W, D) combinations:

  DD1  accel(W=4) D=30
  DD2  accel(W=4) D=50
  DD3  accel(W=3) D=35
  DD4  accel(W=5) D=40 (new W=5, untested)
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
log = logging.getLogger("r29")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.75
FITNESS_FLOOR = 1.25
TURNOVER_CEILING = 0.20

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


def expr(w: int, d: int) -> str:
    return (f"zscore(reverse(ts_decay_linear(multiply("
            f"subtract(returns, ts_delay(returns, {w})), {VOLWEIGHT}), {d})))")


VARIANTS = [
    {"label": "DD1_accel4_D30", "W": 4, "D": 30},
    {"label": "DD2_accel4_D50", "W": 4, "D": 50},
    {"label": "DD3_accel3_D35", "W": 3, "D": 35},
    {"label": "DD4_accel5_D40", "W": 5, "D": 40},
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r29_fresh_accel_more_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"2+ more NEW alphas SH>={SHARPE_FLOOR} TO<{TURNOVER_CEILING} FIT>{FITNESS_FLOOR}.\n"
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
            "variant": v["label"], "W": v["W"], "D": v["D"],
            "expression": expression, **res,
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

    md = f"# Round 29 - more fresh accel alphas\n\n"
    md += f"## Results (ranked by SH)\n\n"
    md += f"| variant | W | D | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---:|---:|---:|---:|---:|---:|---:|---|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: r["sharpe"], reverse=True)
    survivors = []
    for r in ok_results:
        passes = (r["sharpe"] >= SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                  and r["turnover"] < TURNOVER_CEILING)
        tag = "**YES**" if passes else "no"
        if passes:
            survivors.append(r)
        md += (f"| {r['variant']} | {r['W']} | {r['D']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['W']} | {r['D']} | FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "fresh_accel_more_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
