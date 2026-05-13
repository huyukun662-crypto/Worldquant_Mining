"""Round 43: micro-tune to find a 3rd NEW PV alpha at SH>=1.75 TO<0.2 FIT>1.25.

Have: PP3 (RRNL3xLz) SH=1.77, QQ4 (rKbmv7q8) SH=1.77. Need 1 more.

R42 near-misses to push:
  QQ1 vof=20 acc=1 D=20: SH=1.76 TO=0.203 -- pull TO down by extending D
  QQ3 vof=10 acc=1 D=30: SH=1.69 -- raise SH
  QQ5 vof=20 acc=3 D=30: SH=1.73 -- raise SH

5 micro-variants:
  RR1  vof=20 acc=1 D=22  (extend D=20 slightly to drop TO)
  RR2  vof=15 acc=2 D=30  (between vof=10 and vof=20)
  RR3  vof=20 acc=2 D=25  (shorter D for higher SH)
  RR4  vof=20 acc=2 D=35  (slight longer D)
  RR5  vof=25 acc=2 D=30  (longer vof inner)
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r43")
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
    {"label": "RR1_vof20_acc1_D22", "vof_w": 20, "accel_w": 1, "d": 22},
    {"label": "RR2_vof15_acc2_D30", "vof_w": 15, "accel_w": 2, "d": 30},
    {"label": "RR3_vof20_acc2_D25", "vof_w": 20, "accel_w": 2, "d": 25},
    {"label": "RR4_vof20_acc2_D35", "vof_w": 20, "accel_w": 2, "d": 35},
    {"label": "RR5_vof25_acc2_D30", "vof_w": 25, "accel_w": 2, "d": 30},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r43_pp3_micro_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text("Micro-tune PP3 for 3rd alpha.\n")
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        expression = expr(v["vof_w"], v["accel_w"], v["d"])
        log.info(f"  [{i}/5] {v['label']}")
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
                     f"FIT={res['fitness']:+.3f}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R43 micro-tune (target SH>=1.75 TO<0.2 FIT>1.25)\n\n"
    md += ("| variant | vof_w | acc_w | D | SH | TO | FIT | survives? |\n"
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
