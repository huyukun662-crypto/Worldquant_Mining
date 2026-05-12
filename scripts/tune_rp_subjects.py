"""Round 35: RavenPack subject sweep + amplification attempts.

R34 confirmed rp_css/ess_earnings work but SH only 0.29-0.36.
R35 tests other RavenPack subjects and amplification tricks:

  JJ1  rp_css_ratings LONG          -- analyst ratings news
  JJ2  rp_css_revenue LONG          -- revenue news
  JJ3  rp_css_mna LONG              -- M&A news
  JJ4  rp_css_earnings D=40 LONG    -- longer decay amplification
  JJ5  rp_css_earnings + snt_social_value compound LONG
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
log = logging.getLogger("r35")

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
    {"label": "JJ1_rp_ratings",
     "expression": "zscore(ts_decay_linear(rp_css_ratings, 20))"},
    {"label": "JJ2_rp_revenue",
     "expression": "zscore(ts_decay_linear(rp_css_revenue, 20))"},
    {"label": "JJ3_rp_mna",
     "expression": "zscore(ts_decay_linear(rp_css_mna, 20))"},
    {"label": "JJ4_rp_earnings_D40",
     "expression": "zscore(ts_decay_linear(rp_css_earnings, 40))"},
    {"label": "JJ5_compound_rp_social",
     "expression": "zscore(ts_decay_linear(add(rp_css_earnings, snt_social_value), 20))"},
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r35_rp_subjects_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "RavenPack subject sweep + amplification.\n"
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

    md = "# R35 - RavenPack subjects + amplification\n\n"
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
