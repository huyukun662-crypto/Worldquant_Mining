"""Round 13: R^2 momentum factor family on USA TOP3000.

"R^2 momentum" / "idiosyncratic momentum" / "residual momentum"
captures the persistent component of returns AFTER stripping the
market/factor exposure. On WQ Brain, INDUSTRY neutralization already
does much of the residualization at the simulation layer.

R4 already tested 40-120d momentum (LONG direction) and found it
DEAD on TOP3000 INDUSTRY-neutralized -- 7/8 variants gave negative
SH. R13 probes the LONGER-HORIZON momentum space (252d) which was
not covered, plus the standard 12-1 skip-month variant, the
risk-adjusted (information-ratio style) form, and the REVERSED
direction (long-horizon mean reversion).

5 variants:
  X1  pure 252d momentum LONG     -- ts_mean(returns, 252)
  X2  12-1 momentum LONG          -- ts_mean(returns, 252) - ts_mean(returns, 21)
  X3  risk-adjusted 252d LONG     -- ts_mean(returns, 252) / ts_std_dev(returns, 252)
  X4  pure 252d REVERSED          -- long-horizon mean reversion
  X5  12-1 momentum REVERSED      -- long-horizon mean reversion w/ skip

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1, pasteurization=ON). Filter: SH>1.3, FIT>1.0, TO<0.2.
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
log = logging.getLogger("r13")

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

MOM_252 = "ts_mean(returns, 252)"
MOM_21 = "ts_mean(returns, 21)"
MOM_12_1 = f"subtract({MOM_252}, {MOM_21})"
VOL_252 = "ts_std_dev(returns, 252)"

VARIANTS = [
    {
        "label": "X1_mom252_long",
        "logic": "pure 252d cumulative return, LONG (no reverse)",
        "expression": f"zscore(ts_decay_linear({MOM_252}, 20))",
    },
    {
        "label": "X2_mom12_1_long",
        "logic": "12-1 skip-month momentum, LONG (Asness convention)",
        "expression": f"zscore(ts_decay_linear({MOM_12_1}, 20))",
    },
    {
        "label": "X3_riskadj_mom252_long",
        "logic": "risk-adjusted 252d momentum (returns / std_dev), LONG",
        "expression": (
            f"zscore(ts_decay_linear(divide({MOM_252}, {VOL_252}), 20))"
        ),
    },
    {
        "label": "X4_mom252_reversed",
        "logic": "252d cumulative return REVERSED (long-horizon mean reversion)",
        "expression": f"zscore(reverse(ts_decay_linear({MOM_252}, 20)))",
    },
    {
        "label": "X5_mom12_1_reversed",
        "logic": "12-1 skip-month REVERSED (mean reversion w/ skip)",
        "expression": f"zscore(reverse(ts_decay_linear({MOM_12_1}, 20)))",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r13_r2_momentum_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"USA TOP3000 R^2/idiosyncratic momentum probe.\n"
        f"5 variants: 252d LONG/REVERSE x {{pure, 12-1 skip, risk-adj}}.\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
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

    md = f"# Round 13 - R^2 momentum family on USA TOP3000\n\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Reference (R4 finding): 40-120d momentum LONG is dead on TOP3000 (7/8 negative SH)\n\n"
    md += f"## Results\n\n"
    md += f"| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['logic']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['logic']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "r2_momentum_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 13 final - R^2 momentum on USA TOP3000\n\n"
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
                         f"- logic: {r['logic']}\n"
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
