"""Round 47: fix marginal CONC=0.123 on R45+R46 alphas (election day 2020-11-05).

Issue: one of the 5 alphas shows CONC=12.26% on 2020-11-05 (close to
0.10 cutoff). Likely culprits are short-decay (ZYjLMa03 D=25) or
short-rv-window (RRNLzN7o rv=10).

5 fix attempts (truncation reduction + SUBINDUSTRY):

  TT1  ZYjLMa03 (D=25) trunc=0.04
  TT2  ZYjLMa03 (D=25) trunc=0.03
  TT3  ZYjLMa03 (D=25) SUBINDUSTRY trunc=0.05
  TT4  RRNLzN7o (rv=10) trunc=0.04
  TT5  RRNLzN7o (rv=10) SUBINDUSTRY trunc=0.05
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r47")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.05, "neutralization": "INDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VOLWT = "log(add(divide(volume, adv20), 1))"


def expr(rv: int, acc: int, d: int) -> str:
    return (f"zscore(reverse(ts_decay_linear(multiply(multiply("
            f"ts_std_dev(returns, {rv}), "
            f"subtract(returns, ts_delay(returns, {acc}))"
            f"), {VOLWT}), {d})))")


# ZYjLMa03 = rv=20, acc=2, D=25
ZY_EXPR = expr(20, 2, 25)
# RRNLzN7o = rv=10, acc=2, D=30
RR_EXPR = expr(10, 2, 30)

VARIANTS = [
    {"label": "TT1_ZY_trunc04",
     "settings": {**BASE, "truncation": 0.04},
     "expression": ZY_EXPR, "logic": "ZYjLMa03 trunc=0.04"},
    {"label": "TT2_ZY_trunc03",
     "settings": {**BASE, "truncation": 0.03},
     "expression": ZY_EXPR, "logic": "ZYjLMa03 trunc=0.03"},
    {"label": "TT3_ZY_SUBIN",
     "settings": {**BASE, "neutralization": "SUBINDUSTRY"},
     "expression": ZY_EXPR, "logic": "ZYjLMa03 SUBINDUSTRY"},
    {"label": "TT4_RR_trunc04",
     "settings": {**BASE, "truncation": 0.04},
     "expression": RR_EXPR, "logic": "RRNLzN7o trunc=0.04"},
    {"label": "TT5_RR_SUBIN",
     "settings": {**BASE, "neutralization": "SUBINDUSTRY"},
     "expression": RR_EXPR, "logic": "RRNLzN7o SUBINDUSTRY"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r47_fix_marginal_conc_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Fix marginal CONC=0.123 on 2020-11-05.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/5] {v['label']}: {v['logic']}")
        log.info(f"      trunc={v['settings']['truncation']} neut={v['settings']['neutralization']}")
        try:
            res = r5.submit(cm.session, v["expression"], v["settings"])
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "logic": v["logic"],
                 "settings": {"truncation": v["settings"]["truncation"],
                              "neutralization": v["settings"]["neutralization"]},
                 "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") == "CONCENTRATED_WEIGHT":
                    log.info(f"        CONC: {chk.get('result')} value={chk.get('value')} date={chk.get('date')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R47 fix marginal CONC\n\n"
    md += ("| variant | logic | SH | TO | FIT | conc | passes? |\n"
           "|---|---|---:|---:|---:|---|---|\n")
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name'] == 'CONCENTRATED_WEIGHT'), {})
        conc_pass = conc.get('result') == 'PASS'
        all_pass = (r['sharpe'] >= 1.75 and r['turnover'] < 0.20
                    and r['fitness'] > 1.25 and conc_pass)
        conc_cell = "PASS" if conc_pass else f"FAIL({conc.get('value','?')}@{conc.get('date','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['logic']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {conc_cell} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | no |\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
