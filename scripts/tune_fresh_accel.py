"""Round 28: NEW alphas at SH>=1.75, TO<0.2, FIT>1.25.

User wants fresh alpha_ids -- nothing reused from R5-R27.
Existing R12/R15/R16 covered: W in {1,2,3}, D in {25,30,40,50,60,80}.
R28 explores untested combinations:

  CC1  accel(W=4) D=40 vol-weighted -- extend W beyond {1,2,3}
  CC2  accel(W=2) D=35 vol-weighted -- bridge D=30/D=40
  CC3  accel(W=2) D=45 vol-weighted -- bridge D=40/D=50
  CC4  accel(W=1) * intraday_return -- cross-family compound
       (combines price-accel + intraday mechanisms, no vol-weight)
  CC5  accel(W=1) * historical_volatility_20 D=40
       -- option-realized vol weight instead of log(vol/adv20+1)

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1, pasteurization=ON, nanHandling=OFF).

Filter: SH>=1.75, FIT>1.25, TO<0.20.
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
log = logging.getLogger("r28")

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
INTRADAY = "divide(subtract(close, open), open)"


def accel(w: int) -> str:
    return f"subtract(returns, ts_delay(returns, {w}))"


VARIANTS = [
    {
        "label": "CC1_accel4_D40",
        "logic": "accel(W=4) vol-weighted, D=40 (extend W beyond {1,2,3})",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(4)}, {VOLWEIGHT}), 40)))"
        ),
    },
    {
        "label": "CC2_accel2_D35",
        "logic": "accel(W=2) vol-weighted, D=35 (bridge 30/40)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(2)}, {VOLWEIGHT}), 35)))"
        ),
    },
    {
        "label": "CC3_accel2_D45",
        "logic": "accel(W=2) vol-weighted, D=45 (bridge 40/50)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(2)}, {VOLWEIGHT}), 45)))"
        ),
    },
    {
        "label": "CC4_accel_x_intraday",
        "logic": "accel(W=1) x (close-open)/open compound, D=40 (no vol weight)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(1)}, {INTRADAY}), 40)))"
        ),
    },
    {
        "label": "CC5_accel_x_histvol",
        "logic": "accel(W=1) x historical_volatility_20, D=40 (alt vol weight)",
        "expression": (
            f"zscore(reverse(ts_decay_linear("
            f"multiply({accel(1)}, historical_volatility_20), 40)))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r28_fresh_accel_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"5 NEW alphas SH>={SHARPE_FLOOR}, TO<{TURNOVER_CEILING}, FIT>{FITNESS_FLOOR}.\n"
        f"All untested W/D combos or new compound forms.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      logic: {v['logic']}")
        log.info(f"      expr:  {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "logic": v["logic"],
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

    md = f"# Round 28 - NEW alphas SH>={SHARPE_FLOOR} TO<{TURNOVER_CEILING} FIT>{FITNESS_FLOOR}\n\n"
    md += f"## Results (ranked by SH)\n\n"
    md += f"| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: r["sharpe"], reverse=True)
    survivors = []
    for r in ok_results:
        passes = (r["sharpe"] >= SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                  and r["turnover"] < TURNOVER_CEILING)
        tag = "**YES**" if passes else "no"
        if passes:
            survivors.append(r)
        md += (f"| {r['variant']} | {r['logic']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "fresh_accel_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
