"""Round 38: amplify LL5 actual_eps_value_quarterly (SH=0.67 but checks fail).

  MM1  ts_zscore(actual_eps_value_quarterly, 60) -- dynamic, may pass checks
  MM2  actual_eps_value_quarterly * snt_social_volume -- dilute with dense
  MM3  actual_eps_value_quarterly with D=60 -- heavy smoothing
  MM4  actual_eps - rp_css_earnings (surprise vs expectation)
  MM5  reverse(actual_eps_value_quarterly) -- mean reversion direction
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r38")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

EPS = "actual_eps_value_quarterly"

VARIANTS = [
    {"label": "MM1_eps_tszscore",
     "expression": f"zscore(ts_decay_linear(ts_zscore({EPS}, 60), 20))"},
    {"label": "MM2_eps_x_socvol",
     "expression": f"zscore(ts_decay_linear(multiply({EPS}, snt_social_volume), 20))"},
    {"label": "MM3_eps_D60",
     "expression": f"zscore(ts_decay_linear({EPS}, 60))"},
    {"label": "MM4_eps_minus_rp",
     "expression": f"zscore(ts_decay_linear(subtract({EPS}, rp_css_earnings), 20))"},
    {"label": "MM5_eps_reversed",
     "expression": f"zscore(reverse(ts_decay_linear({EPS}, 20)))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r38_eps_amplify_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text("Amplify LL5 actual_eps SH=0.67.\n")
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
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
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R38\n\n| variant | SH | TO | FIT | conc | sub-uni |\n|---|---:|---:|---:|---|---|\n"
    for r in results:
        if r.get("ok"):
            conc = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
            sub = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
            md += (f"| {r['variant']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                    f"{r['fitness']:+.3f} | {conc.get('result','-')} | {sub.get('result','-')} |\n")
        else:
            md += f"| {r['variant']} | - | - | - | - | - |\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
