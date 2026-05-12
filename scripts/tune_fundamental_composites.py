"""Round 23: dense fundamental composites for WQ-check-compliant non-PV alphas.

After 6 rounds (R20-R22) confirmed option-IV alphas cannot pass
WQ's CONCENTRATED_WEIGHT check (data sparsity is structural on
this account), pivot to fundamental fields which are populated for
nearly all TOP3000 names.

Trade-off: fundamental alphas have lower raw SH (R14/R17 max was
0.48) but should pass all WQ checks since data is dense.

5 composites (each is logically and structurally distinct):

  V1  Quality composite: gross_profitability + ROE - asset_growth (LONG)
       -- F&F-style multi-anomaly quality
  V2  PB reversed (long value): close/bookvalue_ps REVERSED
       -- value tilt
  V3  Earnings quality: cashflow_op / income (LONG)
       -- cash-backed earnings outperform
  V4  Operating margin: operating_income / revenue (LONG)
       -- profitability
  V5  ROIC: operating_income / invested_capital (LONG)
       -- return on invested capital

Settings: zscore wrapper, SUBINDUSTRY neut (R20 showed best),
truncation=0.05, decay=8, TOP3000, delay=1, nanHandling=ON.

Filter: pass ALL WQ checks (CONCENTRATED_WEIGHT, LOW_SUB_UNIVERSE_SHARPE,
etc.) and SH > 0.5 (realistic for fundamentals).
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
log = logging.getLogger("r23")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 8,
    "truncation": 0.05,
    "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

GP = "divide(subtract(revenue, cogs), assets)"
ROE = "return_equity"
ASSET_GROWTH = (
    "divide(subtract(assets, ts_delay(assets, 252)), ts_delay(assets, 252))"
)
PB = "divide(close, bookvalue_ps)"
EARN_QUALITY = "divide(cashflow_op, income)"
OP_MARGIN = "divide(operating_income, revenue)"
ROIC = "divide(operating_income, invested_capital)"

VARIANTS = [
    {
        "label": "V1_quality_composite",
        "logic": "GP + ROE - asset_growth (F&F-style)",
        "expression": (
            f"zscore(ts_decay_linear("
            f"subtract(add({GP}, {ROE}), {ASSET_GROWTH}), 20))"
        ),
    },
    {
        "label": "V2_PB_reversed",
        "logic": "PB reversed (long cheap stocks)",
        "expression": f"zscore(reverse(ts_decay_linear({PB}, 20)))",
    },
    {
        "label": "V3_earnings_quality",
        "logic": "cashflow_op / income LONG (cash-backed earnings)",
        "expression": f"zscore(ts_decay_linear({EARN_QUALITY}, 20))",
    },
    {
        "label": "V4_operating_margin",
        "logic": "operating_income / revenue LONG",
        "expression": f"zscore(ts_decay_linear({OP_MARGIN}, 20))",
    },
    {
        "label": "V5_ROIC",
        "logic": "operating_income / invested_capital LONG",
        "expression": f"zscore(ts_decay_linear({ROIC}, 20))",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r23_fund_composites_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Dense fundamental composites for WQ-check-compliant non-PV alphas.\n"
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
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} "
                             f"limit={chk.get('limit')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = f"# Round 23 - dense fundamental composites\n\n"
    md += f"## Results (ranked by SH)\n\n"
    md += f"| variant | logic | SH | TO | FIT | conc | sub-uni | checks |\n"
    md += f"|---|---|---:|---:|---:|---|---|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: r["sharpe"], reverse=True)
    survivors = []
    for r in ok_results:
        conc = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
        sub = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
        conc_ok = conc.get("result") == "PASS"
        sub_ok = sub.get("result") == "PASS"
        if conc_ok and sub_ok and r["sharpe"] > 0.5:
            survivors.append(r)
        conc_val = conc.get("value", "?")
        sub_val = sub.get("value", "?")
        conc_cell = "PASS" if conc_ok else f"FAIL ({conc_val})"
        sub_cell = "PASS" if sub_ok else f"FAIL ({sub_val})"
        md += (f"| {r['variant']} | {r['logic']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{conc_cell} | {sub_cell} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | - |\n")
    md += f"\n**Pass all checks + SH>0.5: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "fund_composites_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
