"""Round 26: probe what NEW account (2841262992@qq.com) can access.

Old account (fin2309361@xmu.edu.my) had broader Model field access.
New account is more restricted. R25 confirmed:
  - beta_last_60_days_spy: ACCESSIBLE (SH=0.01 near-zero)
  - distress_risk_measure: BLOCKED
  - equity_value_score: BLOCKED
  - fcf_yield_times_forward_roe: BLOCKED
  - consensus_analyst_rating: BLOCKED

R26 retests fields known to work on the OLD account, on the NEW account:

  AA1  earnings_quality (cashflow_op / income, V3 from R23, SH=0.67)
  AA2  asset_growth REVERSED (P5 from R17, SH=0.48)
  AA3  correlation_60d_spy REVERSED (low-correlation anomaly)
  AA4  snt_social_value LONG (Q3 from R18, SH=0.33)
  AA5  bookvalue_ps / close LONG (F1 from R14, SH=0.47)

Goal: identify which fields are accessible on new account so we can
plan R27 with viable candidates.
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
log = logging.getLogger("r26")

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

VARIANTS = [
    {
        "label": "AA1_earnings_quality",
        "logic": "cashflow_op / income LONG (V3 retry)",
        "expression": "zscore(ts_decay_linear(divide(cashflow_op, income), 20))",
    },
    {
        "label": "AA2_asset_growth_rev",
        "logic": "252d asset growth REVERSED (P5 retry)",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "divide(subtract(assets, ts_delay(assets, 252)), "
            "ts_delay(assets, 252)), 20)))"
        ),
    },
    {
        "label": "AA3_correlation_60d_rev",
        "logic": "60d corr w/ SPY REVERSED (low-corr LONG)",
        "expression": (
            "zscore(reverse(ts_decay_linear(correlation_last_60_days_spy, 20)))"
        ),
    },
    {
        "label": "AA4_social_sent_long",
        "logic": "snt_social_value LONG (Q3 retry)",
        "expression": "zscore(ts_decay_linear(snt_social_value, 20))",
    },
    {
        "label": "AA5_BM_long",
        "logic": "book-to-market LONG (cheap stocks)",
        "expression": "zscore(ts_decay_linear(divide(bookvalue_ps, close), 20))",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r26_new_account_probe_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Probe what non-PV fields the new account can access.\n"
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

    md = f"# Round 26 - new account field access probe\n\n"
    md += f"## Results\n\n"
    md += f"| variant | logic | SH | TO | FIT | conc | sub-uni | status |\n"
    md += f"|---|---|---:|---:|---:|---|---|---|\n"
    for r in results:
        if r.get("ok"):
            conc = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
            sub = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
            conc_ok = conc.get("result") == "PASS"
            sub_ok = sub.get("result") == "PASS"
            conc_val = conc.get("value", "?")
            sub_val = sub.get("value", "?")
            conc_cell = "PASS" if conc_ok else f"FAIL ({conc_val})"
            sub_cell = "PASS" if sub_ok else f"FAIL ({sub_val})"
            md += (f"| {r['variant']} | {r['logic']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{conc_cell} | {sub_cell} | ok |\n")
        else:
            err = str(r.get('error', '?'))[:60]
            md += (f"| {r['variant']} | {r['logic']} | - | - | - | - | - | BLOCKED/{err} |\n")
    (session_dir / "outputs" / "new_account_probe.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
