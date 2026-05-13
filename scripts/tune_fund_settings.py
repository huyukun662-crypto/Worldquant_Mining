"""Round 50: rescue fundamental alphas via universe/truncation/pasteurization tuning.

Target: SH>=1.75, TO<0.20, FIT>1.25, all WQ checks pass.
All settings adjustable except region (USA fixed).

Strongest fundamental candidates from R17-R49:
  actual_eps_value_quarterly D=60: SH=0.71 (conc fail at TOP3000)
  trade_when cashflow_op rev: SH=1.59 (TO=0.59 at TOP3000)
  earnings_quality LONG: SH=0.67 (sub-uni fail at TOP3000)
  XX1 E/P x reversal: SH=0.42 (sub-uni fail)

5 settings-tuned attempts targeting smaller, denser universes:

  YY1  actual_eps D=60 / TOP500 / SUBINDUSTRY / trunc=0.04 / past=ON
  YY2  actual_eps D=60 / TOP200 / SUBINDUSTRY / trunc=0.04 / past=ON
  YY3  trade_when CF rev / TOP500 / SUBINDUSTRY / trunc=0.05 (tight univ for TO)
  YY4  E/P x accel D=25 / TOP500 / SUBINDUSTRY / trunc=0.04
  YY5  earnings_quality D=20 / TOP200 / SUBINDUSTRY / trunc=0.04 / past=OFF
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r50")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(universe="TOP3000", neut="SUBINDUSTRY", trunc=0.05, past="ON"):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": universe,
        "delay": 1, "decay": 8, "truncation": trunc, "neutralization": neut,
        "pasteurization": past, "unitHandling": "VERIFY", "nanHandling": "ON",
        "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
        "testPeriod": "P0Y0M",
    }


EPS = "actual_eps_value_quarterly"
EARN_Q = "divide(cashflow_op, income)"
EP = "divide(eps, close)"
ACCEL = "subtract(returns, ts_delay(returns, 2))"

VARIANTS = [
    {"label": "YY1_eps_D60_TOP500_SUBIN",
     "settings": settings("TOP500", "SUBINDUSTRY", 0.04, "ON"),
     "expression": f"zscore(ts_decay_linear({EPS}, 60))",
     "logic": "actual_eps D=60 / TOP500 / SUBIN / trunc=0.04"},
    {"label": "YY2_eps_D60_TOP200_SUBIN",
     "settings": settings("TOP200", "SUBINDUSTRY", 0.04, "ON"),
     "expression": f"zscore(ts_decay_linear({EPS}, 60))",
     "logic": "actual_eps D=60 / TOP200 / SUBIN / trunc=0.04"},
    {"label": "YY3_tradewhen_CF_TOP500",
     "settings": settings("TOP500", "SUBINDUSTRY", 0.05, "ON"),
     "expression": (
         "trade_when(greater(cashflow_op, 0), "
         "zscore(reverse(ts_zscore(returns, 5))), 0)"),
     "logic": "trade_when CF rev / TOP500 / SUBIN"},
    {"label": "YY4_EP_accel_TOP500_SUBIN",
     "settings": settings("TOP500", "SUBINDUSTRY", 0.04, "ON"),
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply({EP}, {ACCEL}), 25)))"),
     "logic": "E/P x accel D=25 / TOP500 / SUBIN / trunc=0.04"},
    {"label": "YY5_earnQ_TOP200_pastOFF",
     "settings": settings("TOP200", "SUBINDUSTRY", 0.04, "OFF"),
     "expression": f"zscore(ts_decay_linear({EARN_Q}, 20))",
     "logic": "earnings_quality / TOP200 / SUBIN / past=OFF"},
]


def _load(p, name):
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r50_fund_settings_tune_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Rescue fundamentals via universe/truncation/pasteurization tuning.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/5] {v['label']}: {v['logic']}")
        log.info(f"      universe={v['settings']['universe']} neut={v['settings']['neutralization']} "
                 f"trunc={v['settings']['truncation']} past={v['settings']['pasteurization']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], v["settings"])
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "logic": v["logic"],
                 "settings": {k: v["settings"][k] for k in
                              ["universe", "neutralization", "truncation", "pasteurization"]},
                 "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R50 fundamental settings tune\n\n"
    md += ("| variant | logic | SH | TO | FIT | conc | sub-uni | passes? |\n"
           "|---|---|---:|---:|---:|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        conc_ok = conc.get('result') == 'PASS'
        sub_ok = sub.get('result') == 'PASS'
        all_pass = (r['sharpe'] >= 1.75 and r['turnover'] < 0.20
                    and r['fitness'] > 1.25 and conc_ok and sub_ok)
        if all_pass:
            survivors.append(r)
        conc_cell = "PASS" if conc_ok else f"FAIL({conc.get('value','?')})"
        sub_cell = "PASS" if sub_ok else f"FAIL({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['logic']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {conc_cell} | "
                f"{sub_cell} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
