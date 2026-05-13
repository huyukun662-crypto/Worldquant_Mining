"""Round 46: extend UU4 (realized-return-vol * accel * volwt) for 2+ more passing alphas.

R45 UU4 (9q9Qd86V): ts_std_dev(returns,20) * accel(W=2) * volwt D=30
  SH=2.29 TO=0.159 FIT=4.58 conc=PASS sub-uni=1.98 (everything passes)

5 sibling variants:
  VV1  ts_std_dev(returns, 10) * accel(W=2) * volwt D=30 (short vol window)
  VV2  ts_std_dev(returns, 30) * accel(W=2) * volwt D=30 (long vol window)
  VV3  ts_std_dev(returns, 20) * accel(W=1) * volwt D=30 (short accel)
  VV4  ts_std_dev(returns, 20) * accel(W=2) * volwt D=25 (short outer)
  VV5  ts_std_dev(returns, 20) * accel(W=2) * volwt D=40 (long outer)
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r46")
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


def expr(retvol_w: int, accel_w: int, d: int) -> str:
    retvol = f"ts_std_dev(returns, {retvol_w})"
    accel = f"subtract(returns, ts_delay(returns, {accel_w}))"
    return f"zscore(reverse(ts_decay_linear(multiply(multiply({retvol}, {accel}), {VOLWT}), {d})))"


VARIANTS = [
    {"label": "VV1_rv10_acc2_D30", "retvol_w": 10, "accel_w": 2, "d": 30},
    {"label": "VV2_rv30_acc2_D30", "retvol_w": 30, "accel_w": 2, "d": 30},
    {"label": "VV3_rv20_acc1_D30", "retvol_w": 20, "accel_w": 1, "d": 30},
    {"label": "VV4_rv20_acc2_D25", "retvol_w": 20, "accel_w": 2, "d": 25},
    {"label": "VV5_rv20_acc2_D40", "retvol_w": 20, "accel_w": 2, "d": 40},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r46_uu4_extensions_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Extend UU4 (ret-vol * accel * volwt) for 2+ more passing alphas.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        expression = expr(v["retvol_w"], v["accel_w"], v["d"])
        log.info(f"  [{i}/5] {v['label']}")
        log.info(f"      expr: {expression}")
        try:
            res = r5.submit(cm.session, expression, BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], **v, "expression": expression, **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") == "CONCENTRATED_WEIGHT":
                    log.info(f"        CONC: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R46 UU4 extensions (target SH>=1.75 TO<0.2 FIT>1.25 CONC PASS)\n\n"
    md += ("| variant | rv_w | acc_w | D | SH | TO | FIT | conc | survives? |\n"
           "|---|---:|---:|---:|---:|---:|---:|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name'] == 'CONCENTRATED_WEIGHT'), {})
        conc_pass = conc.get('result') == 'PASS'
        all_pass = (r['sharpe'] >= 1.75 and r['turnover'] < 0.20
                    and r['fitness'] > 1.25 and conc_pass)
        if all_pass:
            survivors.append(r)
        conc_cell = "PASS" if conc_pass else f"FAIL({conc.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['retvol_w']} | {r['accel_w']} | {r['d']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{conc_cell} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | - | - | - | FAIL | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
