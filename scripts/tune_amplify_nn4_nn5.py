"""Round 40: amplify R39/NN4 + NN5 (both ~1.5 SH, need +0.25 to hit 1.75).

R39 found two strong NEW structures:
  NN4 vol-of-vol rev D=30:    SH=+1.560 TO=0.087 FIT=+2.270
  NN5 ret*range*volwt rev D=20: SH=+1.510 TO=0.175 FIT=+2.500

R40 sweeps decay and inner windows to push SH past 1.75:

  OO1  NN4 vol-of-vol inner W=10, D=30
  OO2  NN4 vol-of-vol inner W=60, D=30
  OO3  NN4 vol-of-vol, D=50 (longer outer)
  OO4  NN5 ret*range*volwt, D=30
  OO5  NN5 ret*range*volwt, D=40
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r40")
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
RANGE = "divide(subtract(high, low), close)"


def vof(w_inner: int, d_outer: int) -> str:
    return (f"zscore(reverse(ts_decay_linear("
            f"ts_std_dev(divide(volume, adv20), {w_inner}), {d_outer})))")


def nn5_compound(d: int) -> str:
    return (f"zscore(reverse(ts_decay_linear(multiply(multiply(returns, "
            f"{RANGE}), {VOLWT}), {d})))")


VARIANTS = [
    {"label": "OO1_vof_W10_D30", "logic": "vol-of-vol W=10 inner, D=30",
     "expression": vof(10, 30)},
    {"label": "OO2_vof_W60_D30", "logic": "vol-of-vol W=60 inner, D=30",
     "expression": vof(60, 30)},
    {"label": "OO3_vof_W20_D50", "logic": "vol-of-vol W=20, D=50 (longer outer)",
     "expression": vof(20, 50)},
    {"label": "OO4_compound_D30", "logic": "ret*range*volwt D=30",
     "expression": nn5_compound(30)},
    {"label": "OO5_compound_D40", "logic": "ret*range*volwt D=40",
     "expression": nn5_compound(40)},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r40_amplify_nn4_nn5_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Amplify NN4 vol-of-vol + NN5 ret*range*volwt past SH=1.75.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: {v['logic']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "logic": v["logic"],
                 "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} RET={res['returns']:+.3f}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R40 amplification\n\n| variant | SH | TO | FIT | survives 1.75? |\n|---|---:|---:|---:|---|\n"
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        passes = r['sharpe'] >= 1.75 and r['turnover'] < 0.20 and r['fitness'] > 1.25
        tag = "**YES**" if passes else "no"
        md += (f"| {r['variant']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | FAIL | - | - | no |\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
