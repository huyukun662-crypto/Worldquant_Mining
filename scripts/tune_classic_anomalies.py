"""Round 17: classical fundamental anomalies on USA TOP3000.

Stop mining price-volume signals. R17 tests 5 well-documented
fundamental factor anomalies. Fields used (verified in
constants/data_fields_cache_USA_1_TOP3000.json):
  assets, equity, revenue, cogs, eps, cashflow_op, capex,
  enterprise_value, income, liabilities

Variants:
  P1 Accruals REVERSED   (Sloan 1996):
       (income - cashflow_op) / assets, REVERSED
       -- stocks with high accruals (more profits than cash) UNDER-perform
  P2 Gross profitability LONG (Novy-Marx 2013):
       (revenue - cogs) / assets, LONG
       -- profitable stocks outperform
  P3 Earnings yield LONG (Basu 1977):
       eps / close, LONG
       -- cheap E/P stocks outperform
  P4 FCF yield LONG:
       (cashflow_op - capex) / enterprise_value, LONG
       -- high free cash flow yield outperforms
  P5 Asset growth REVERSED (Cooper-Gulen-Schill 2008):
       (assets - ts_delay(assets, 252)) / ts_delay(assets, 252), REVERSED
       -- companies that grow assets fast under-perform

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000,
delay=1, nanHandling=ON for sparse fundamental fields.

Filter for triage: SH > 0.5 (below SH=2 user-bar but realistic for
fundamentals; will iterate if any clear).
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
log = logging.getLogger("r17")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

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
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VARIANTS = [
    {
        "label": "P1_accruals_rev",
        "anomaly": "Accruals (Sloan 1996)",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "divide(subtract(income, cashflow_op), assets), 20)))"
        ),
    },
    {
        "label": "P2_gross_profitability",
        "anomaly": "Gross profitability (Novy-Marx 2013)",
        "expression": (
            "zscore(ts_decay_linear("
            "divide(subtract(revenue, cogs), assets), 20))"
        ),
    },
    {
        "label": "P3_earnings_yield",
        "anomaly": "Earnings yield (Basu 1977)",
        "expression": "zscore(ts_decay_linear(divide(eps, close), 20))",
    },
    {
        "label": "P4_fcf_yield",
        "anomaly": "FCF yield (cashflow_op - capex) / EV",
        "expression": (
            "zscore(ts_decay_linear("
            "divide(subtract(cashflow_op, capex), enterprise_value), 20))"
        ),
    },
    {
        "label": "P5_asset_growth_rev",
        "anomaly": "Asset growth (Cooper-Gulen-Schill 2008)",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "divide(subtract(assets, ts_delay(assets, 252)), "
            "ts_delay(assets, 252)), 20)))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r17_classic_anomalies_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"5 classical fundamental anomalies (accruals/GP/EP/FCF/asset growth).\n"
        f"Diagnostic round; will iterate if any pass.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      anomaly: {v['anomaly']}")
        log.info(f"      expr:    {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "anomaly": v["anomaly"],
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

    md = f"# Round 17 - classical fundamental anomalies\n\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1, nanHandling=ON.\n\n"
    md += f"## Results (ranked by |SH|)\n\n"
    md += f"| variant | anomaly | SH | TO | FIT | RET | DD | checks |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    for r in ok_results:
        md += (f"| {r['variant']} | {r['anomaly']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['anomaly']} | FAIL | - | - | - | - | - |\n")
    (session_dir / "outputs" / "classic_anomalies_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
