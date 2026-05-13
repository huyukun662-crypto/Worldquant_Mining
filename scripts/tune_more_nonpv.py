"""Round 37: untested non-PV signal angles.

  LL1  nws18_bee LONG          -- earnings evaluation score (may be event)
  LL2  nws18_nip LONG          -- narrative impact [-1,+1]
  LL3  rp_css_earnings REVERSE -- mean-reversion of news sentiment
  LL4  anl4_basicconafv110_numest LONG -- analyst coverage breadth
  LL5  actual_eps_value_quarterly LONG -- quarterly EPS surprise level
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r37")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VARIANTS = [
    {"label": "LL1_nws18_bee",
     "expression": "zscore(ts_decay_linear(nws18_bee, 20))"},
    {"label": "LL2_nws18_nip",
     "expression": "zscore(ts_decay_linear(nws18_nip, 20))"},
    {"label": "LL3_rp_earnings_reversed",
     "expression": "zscore(reverse(ts_decay_linear(rp_css_earnings, 20)))"},
    {"label": "LL4_analyst_coverage",
     "expression": "zscore(ts_decay_linear(anl4_basicconafv110_numest, 20))"},
    {"label": "LL5_quarterly_eps",
     "expression": "zscore(ts_decay_linear(actual_eps_value_quarterly, 20))"},
]

def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def main():
    r5 = _load(REPO / "scripts" / "run_5agent_workflow.py", "r5")
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r37_more_nonpv_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text("5 more non-PV angles.\n")
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
        (session_dir / "working" / "results_partial.json").write_text(json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")
    md = "# R37\n\n| variant | SH | TO | FIT | conc | sub-uni | status |\n|---|---:|---:|---:|---|---|---|\n"
    for r in results:
        if r.get("ok"):
            conc = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
            sub = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
            conc_ok = conc.get("result") == "PASS"; sub_ok = sub.get("result") == "PASS"
            md += (f"| {r['variant']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                    f"{r['fitness']:+.3f} | {'P' if conc_ok else 'F'} | {'P' if sub_ok else 'F'} | ok |\n")
        else:
            err = str(r.get('error', '?'))[:60]
            md += f"| {r['variant']} | - | - | - | - | - | {err} |\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
