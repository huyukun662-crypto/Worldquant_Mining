"""Round 30: Model category style composite alphas.

After R25 showed proprietary fields like distress_risk_measure are
blocked on new account, R30 tries the fscore_bfl_* style composites
which are typically built-in scoring families:

  EE1  fscore_bfl_quality LONG     -- earnings quality + stability
  EE2  fscore_bfl_momentum LONG    -- price + analyst momentum composite
  EE3  fscore_bfl_growth LONG      -- medium-term growth composite
  EE4  fscore_bfl_profitability LONG -- profitability composite
  EE5  forward_median_earnings_yield LONG -- value tilt (forward E/P)

Settings: zscore wrapper, SUBINDUSTRY neut, truncation=0.05, decay=8,
TOP3000, delay=1, nanHandling=ON.

Target: at least 1-3 alphas pass ALL WQ checks. If most fields are
blocked, will pivot to other Model fields in R31.
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
log = logging.getLogger("r30")

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
        "label": "EE1_fscore_quality",
        "field": "fscore_bfl_quality",
        "logic": "earnings quality + stability composite LONG",
        "expression": "zscore(ts_decay_linear(fscore_bfl_quality, 20))",
    },
    {
        "label": "EE2_fscore_momentum",
        "field": "fscore_bfl_momentum",
        "logic": "price + analyst momentum composite LONG",
        "expression": "zscore(ts_decay_linear(fscore_bfl_momentum, 20))",
    },
    {
        "label": "EE3_fscore_growth",
        "field": "fscore_bfl_growth",
        "logic": "medium-term growth composite LONG",
        "expression": "zscore(ts_decay_linear(fscore_bfl_growth, 20))",
    },
    {
        "label": "EE4_fscore_profitability",
        "field": "fscore_bfl_profitability",
        "logic": "profitability composite LONG",
        "expression": "zscore(ts_decay_linear(fscore_bfl_profitability, 20))",
    },
    {
        "label": "EE5_forward_earnings_yield",
        "field": "forward_median_earnings_yield",
        "logic": "forward E/P value LONG",
        "expression": "zscore(ts_decay_linear(forward_median_earnings_yield, 20))",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r30_model_fscore_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Probe Model category fscore_bfl_* style composites on new account.\n"
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

    md = f"# Round 30 - Model fscore style composites\n\n"
    md += f"## Results (ranked by |SH|)\n\n"
    md += f"| variant | field | SH | TO | FIT | conc | sub-uni | status |\n"
    md += f"|---|---|---:|---:|---:|---|---|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    for r in ok_results:
        conc = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
        sub = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
        conc_ok = conc.get("result") == "PASS"
        sub_ok = sub.get("result") == "PASS"
        conc_val = conc.get("value", "?")
        sub_val = sub.get("value", "?")
        conc_cell = "PASS" if conc_ok else f"FAIL ({conc_val})"
        sub_cell = "PASS" if sub_ok else f"FAIL ({sub_val})"
        md += (f"| {r['variant']} | `{r['field']}` | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{conc_cell} | {sub_cell} | ok |\n")
    for r in [r for r in results if not r.get("ok")]:
        err = str(r.get('error', '?'))[:60]
        md += (f"| {r['variant']} | `{r['field']}` | - | - | - | - | - | BLOCKED/{err} |\n")
    (session_dir / "outputs" / "model_fscore_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
