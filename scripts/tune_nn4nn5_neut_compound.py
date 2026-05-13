"""Round 41: SUBINDUSTRY neut + compound to push NN4/NN5 past SH=1.75."""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r41")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE_IND = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.08, "neutralization": "INDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}
BASE_SUB = dict(BASE_IND); BASE_SUB["neutralization"] = "SUBINDUSTRY"

VOLWT = "log(add(divide(volume, adv20), 1))"
RANGE = "divide(subtract(high, low), close)"
ACCEL = "subtract(returns, ts_delay(returns, 1))"
VOFVOL_CORE = "ts_std_dev(divide(volume, adv20), 20)"

VARIANTS = [
    {"label": "PP1_nn4_SUBIN", "logic": "NN4 vol-of-vol w/ SUBINDUSTRY",
     "settings": BASE_SUB,
     "expression": f"zscore(reverse(ts_decay_linear({VOFVOL_CORE}, 30)))"},
    {"label": "PP2_nn5_SUBIN", "logic": "NN5 ret*range*volwt w/ SUBINDUSTRY",
     "settings": BASE_SUB,
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply(returns, "
                    f"{RANGE}), {VOLWT}), 20)))")},
    {"label": "PP3_nn4_accel_compound", "logic": "vol-of-vol * accel * volwt rev",
     "settings": BASE_IND,
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply("
                    f"{VOFVOL_CORE}, {ACCEL}), {VOLWT}), 30)))")},
    {"label": "PP4_nn5_D15", "logic": "NN5 with shorter D=15 (higher SH)",
     "settings": BASE_IND,
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply(returns, "
                    f"{RANGE}), {VOLWT}), 15)))")},
    {"label": "PP5_nn4_x_nn5", "logic": "NN4 * NN5 compound: vof*ret*range*volwt rev",
     "settings": BASE_IND,
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply(multiply("
                    f"{VOFVOL_CORE}, returns), {RANGE}), {VOLWT}), 30)))")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r41_nn_neut_compound_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "SUBINDUSTRY neut + compound on NN4/NN5 to break SH=1.75 bar.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: {v['logic']}")
        log.info(f"      neut: {v['settings']['neutralization']}, expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], v["settings"])
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "logic": v["logic"],
                 "neut": v["settings"]["neutralization"],
                 "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R41\n\n| variant | logic | neut | SH | TO | FIT | survives? |\n|---|---|---|---:|---:|---:|---|\n"
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        passes = r['sharpe'] >= 1.75 and r['turnover'] < 0.20 and r['fitness'] > 1.25
        tag = "**YES**" if passes else "no"
        md += (f"| {r['variant']} | {r['logic']} | {r['neut']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | - | FAIL | - | - | no |\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
