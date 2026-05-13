"""Round 36: analyst category fields + non-PV compounds.

After 7 rounds of single-field non-PV alphas capping at SH=0.67,
R36 tests analyst category + multiplicative compounds of two
non-PV signals to amplify.

  KK1  anl4_afv4_eps_mean LONG          -- analyst EPS estimate mean
  KK2  anl4_af_eps_value LONG           -- actual EPS value
  KK3  anl4_basicdetailrec_ratingvalue LONG -- analyst rating (may be event)
  KK4  snt_social_volume * rp_css_earnings compound (R26 + R34 winners)
  KK5  rp_css_earnings * (bookvalue_ps / close) compound (news x value)

If KK1/KK2 work numerically and KK4/KK5 compounds amplify, may exceed
the 0.67 single-field cap.
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
log = logging.getLogger("r36")

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
    {"label": "KK1_anl4_eps_mean",
     "expression": "zscore(ts_decay_linear(anl4_afv4_eps_mean, 20))"},
    {"label": "KK2_anl4_eps_value",
     "expression": "zscore(ts_decay_linear(anl4_af_eps_value, 20))"},
    {"label": "KK3_anl4_rating",
     "expression": "zscore(ts_decay_linear(anl4_basicdetailrec_ratingvalue, 20))"},
    {"label": "KK4_compound_socvol_rpearn",
     "expression": (
         "zscore(ts_decay_linear(multiply(snt_social_volume, rp_css_earnings), 20))"
     )},
    {"label": "KK5_compound_rpearn_btm",
     "expression": (
         "zscore(ts_decay_linear(multiply(rp_css_earnings, "
         "divide(bookvalue_ps, close)), 20))"
     )},
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r36_analyst_compound_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Analyst category + non-PV compounds.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} checks={res['checks_passed']}/{res['checks_total']}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = "# R36 - analyst + non-PV compounds\n\n"
    md += "| variant | SH | TO | FIT | conc | sub-uni | status |\n|---|---:|---:|---:|---|---|---|\n"
    for r in results:
        if r.get("ok"):
            conc = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
            sub = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
            conc_ok = conc.get("result") == "PASS"
            sub_ok = sub.get("result") == "PASS"
            conc_cell = "PASS" if conc_ok else f"FAIL({conc.get('value','?')})"
            sub_cell = "PASS" if sub_ok else f"FAIL({sub.get('value','?')})"
            md += (f"| {r['variant']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                    f"{r['fitness']:+.3f} | {conc_cell} | {sub_cell} | ok |\n")
        else:
            err = str(r.get('error', '?'))[:60]
            md += f"| {r['variant']} | - | - | - | - | - | BLOCKED/{err} |\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
