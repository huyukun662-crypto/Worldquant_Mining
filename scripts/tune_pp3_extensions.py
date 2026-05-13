"""Round 42: extend R41/PP3 (vol-of-vol * accel * volwt rev) for 2+ more.

R41 PP3 (RRNL3xLz): SH=+1.770 TO=0.151 FIT=+3.660 -- first NEW PV alpha
passing SH>=1.75. Expression:
  zscore(reverse(ts_decay_linear(multiply(multiply(
    ts_std_dev(divide(volume, adv20), 20),  # vol-of-vol
    subtract(returns, ts_delay(returns, 1))  # 1-day accel
  ), log(add(divide(volume, adv20), 1))), 30)))

R42 sweeps inner W and outer D plus inner accel W to find more:

  QQ1  vof W=20, accel W=1, D=20  (shorter outer D)
  QQ2  vof W=20, accel W=1, D=40  (longer outer D)
  QQ3  vof W=10, accel W=1, D=30  (shorter inner W)
  QQ4  vof W=20, accel W=2, D=30  (longer accel W)
  QQ5  vof W=20, accel W=3, D=30  (longer accel W)
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r42")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.08, "neutralization": "INDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VOLWT = "log(add(divide(volume, adv20), 1))"


def expr(vof_w: int, accel_w: int, d: int) -> str:
    vof = f"ts_std_dev(divide(volume, adv20), {vof_w})"
    accel = f"subtract(returns, ts_delay(returns, {accel_w}))"
    return f"zscore(reverse(ts_decay_linear(multiply(multiply({vof}, {accel}), {VOLWT}), {d})))"


VARIANTS = [
    {"label": "QQ1_vofW20_acc1_D20", "vof_w": 20, "accel_w": 1, "d": 20},
    {"label": "QQ2_vofW20_acc1_D40", "vof_w": 20, "accel_w": 1, "d": 40},
    {"label": "QQ3_vofW10_acc1_D30", "vof_w": 10, "accel_w": 1, "d": 30},
    {"label": "QQ4_vofW20_acc2_D30", "vof_w": 20, "accel_w": 2, "d": 30},
    {"label": "QQ5_vofW20_acc3_D30", "vof_w": 20, "accel_w": 3, "d": 30},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r42_pp3_extensions_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Extend PP3 (vof*accel*volwt) for 2+ more SH>=1.75 alphas.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        expression = expr(v["vof_w"], v["accel_w"], v["d"])
        log.info(f"  [{i}/5] {v['label']}: vof_w={v['vof_w']} accel_w={v['accel_w']} D={v['d']}")
        log.info(f"      expr: {expression}")
        try:
            res = r5.submit(cm.session, expression, BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "vof_w": v["vof_w"], "accel_w": v["accel_w"],
                 "d": v["d"], "expression": expression, **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} RET={res['returns']:+.3f}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R42 PP3 extensions (target SH>=1.75 TO<0.2 FIT>1.25)\n\n"
    md += ("| variant | vof_w | accel_w | D | SH | TO | FIT | survives? |\n"
           "|---|---:|---:|---:|---:|---:|---:|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        passes = r['sharpe'] >= 1.75 and r['turnover'] < 0.20 and r['fitness'] > 1.25
        tag = "**YES**" if passes else "no"
        if passes:
            survivors.append(r)
        md += (f"| {r['variant']} | {r['vof_w']} | {r['accel_w']} | {r['d']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | - | - | - | FAIL | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
