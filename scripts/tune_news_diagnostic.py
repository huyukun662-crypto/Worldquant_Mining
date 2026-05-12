"""Round 33: news field diagnostic + iteration.

R32 hung on rp_css_earnings for 30+ min (silent block).
R33 mixes known-working + new news fields to map what responds:

  HH1  snt_social_value (KNOWN WORK, R26/R27 baseline) -- account check
  HH2  nws18_qep                                       -- new news polarity
  HH3  nws18_relevance                                  -- relevance score
  HH4  news_eps_actual                                  -- numeric news data
  HH5  nws18_event_relevance                            -- event relevance

If HH1 succeeds, account is alive. HH2-5 map news accessibility.
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
log = logging.getLogger("r33")

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
    {"label": "HH1_snt_social_value", "field": "snt_social_value",
     "expression": "zscore(ts_decay_linear(snt_social_value, 20))"},
    {"label": "HH2_nws18_qep", "field": "nws18_qep",
     "expression": "zscore(ts_decay_linear(nws18_qep, 20))"},
    {"label": "HH3_nws18_relevance", "field": "nws18_relevance",
     "expression": "zscore(ts_decay_linear(nws18_relevance, 20))"},
    {"label": "HH4_news_eps_actual", "field": "news_eps_actual",
     "expression": "zscore(ts_decay_linear(news_eps_actual, 20))"},
    {"label": "HH5_nws18_event_relevance", "field": "nws18_event_relevance",
     "expression": "zscore(ts_decay_linear(nws18_event_relevance, 20))"},
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r33_news_diagnostic_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Diagnose which news/social fields respond on new account.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  field={v['field']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "field": v["field"],
                 "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} checks={res['checks_passed']}/{res['checks_total']}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} "
                             f"value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = "# R33 - news/sentiment diagnostic\n\n"
    md += "| variant | field | SH | TO | FIT | checks | status |\n|---|---|---:|---:|---:|---|---|\n"
    for r in results:
        if r.get("ok"):
            md += (f"| {r['variant']} | `{r['field']}` | {r['sharpe']:+.3f} | "
                    f"{r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | ok |\n")
        else:
            err = str(r.get('error', '?'))[:80]
            md += f"| {r['variant']} | `{r['field']}` | - | - | - | - | BLOCKED/{err} |\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
