"""Round 25: Model category fields (value_score=7, 3281 fields).

After R17-R24 confirmed fundamentals weak and IV skew can't pass
concentration checks, R25 explores the Model category (the
WQ-screenshot reported value_score=7, highest tied with Sentiment).

Model fields are pre-computed composite signals that are typically
densely populated. 5 hand-picked candidates spanning different
mechanism classes:

  Z1  beta_last_60_days_spy REVERSED -- low-beta anomaly LONG
  Z2  distress_risk_measure REVERSED -- low-distress / quality LONG
  Z3  equity_value_score LONG -- proprietary value composite
  Z4  fcf_yield_times_forward_roe LONG -- value x quality compound
  Z5  consensus_analyst_rating LONG -- bullish recs LONG

Settings: zscore wrapper, SUBINDUSTRY neut, truncation=0.05, decay=8,
TOP3000, delay=1, nanHandling=ON.

Target: at least 1-3 alphas pass ALL WQ checks (CONCENTRATED_WEIGHT,
LOW_SUB_UNIVERSE_SHARPE) with reasonable SH.
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
log = logging.getLogger("r25")

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
        "label": "Z1_low_beta",
        "logic": "low-beta anomaly: SPY beta REVERSED",
        "field": "beta_last_60_days_spy",
        "expression": (
            "zscore(reverse(ts_decay_linear(beta_last_60_days_spy, 20)))"
        ),
    },
    {
        "label": "Z2_low_distress",
        "logic": "low-distress quality: distress_risk_measure REVERSED",
        "field": "distress_risk_measure",
        "expression": (
            "zscore(reverse(ts_decay_linear(distress_risk_measure, 20)))"
        ),
    },
    {
        "label": "Z3_equity_value_score",
        "logic": "proprietary value composite LONG",
        "field": "equity_value_score",
        "expression": (
            "zscore(ts_decay_linear(equity_value_score, 20))"
        ),
    },
    {
        "label": "Z4_fcfyield_forward_roe",
        "logic": "FCF yield x forward ROE LONG (value x quality)",
        "field": "fcf_yield_times_forward_roe",
        "expression": (
            "zscore(ts_decay_linear(fcf_yield_times_forward_roe, 20))"
        ),
    },
    {
        "label": "Z5_consensus_rating",
        "logic": "analyst consensus rating LONG",
        "field": "consensus_analyst_rating",
        "expression": (
            "zscore(ts_decay_linear(consensus_analyst_rating, 20))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r25_model_fields_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Probe Model category (value_score=7) fields for non-PV alphas.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      field: {v['field']}")
        log.info(f"      logic: {v['logic']}")
        log.info(f"      expr:  {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "field": v["field"],
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

    md = f"# Round 25 - Model category fields\n\n"
    md += f"## Results (ranked by SH)\n\n"
    md += f"| variant | logic | field | SH | TO | FIT | conc | sub-uni | checks |\n"
    md += f"|---|---|---|---:|---:|---:|---|---|---|\n"
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
        md += (f"| {r['variant']} | {r['logic']} | `{r['field']}` | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{conc_cell} | {sub_cell} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['logic']} | `{r['field']}` | FAIL | - | - | - | - | - |\n")
    md += f"\n**Pass all checks + SH>0.5: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "model_fields_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
