"""Round 53: 5 alphas with COMPLETELY different skeletons.

Avoided skeleton: zscore(reverse(ts_decay_linear(multiply(inner, weight), D)))
                  (canonical R5-R52 form)

5 fresh skeletons:
  BBB1  ts_sum smoothing instead of ts_decay_linear
  BBB2  scale() wrapper + NO decay (instant signal)
  BBB3  signed_power amplifier
  BBB4  group_neutralize inner + standard smoothing
  BBB5  reverse INSIDE (not outside ts_decay_linear)

All keep PV signals but skeleton differs.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r53")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VOLWT = "log(add(divide(volume, adv20), 1))"
ACCEL1 = "subtract(returns, ts_delay(returns, 1))"
REV5 = "ts_zscore(returns, 5)"

VARIANTS = [
    {"label": "BBB1_ts_sum_smoothing",
     "logic": "ts_sum instead of ts_decay_linear",
     "expression": (
         f"zscore(reverse(ts_sum(multiply({ACCEL1}, {VOLWT}), 25)))")},
    {"label": "BBB2_scale_no_decay",
     "logic": "scale wrapper + NO decay (instant signal)",
     "expression": (
         f"scale(reverse(multiply({REV5}, {VOLWT})))")},
    {"label": "BBB3_signed_power",
     "logic": "signed_power transform of accel signal",
     "expression": (
         f"zscore(reverse(ts_decay_linear(signed_power(multiply("
         f"{ACCEL1}, {VOLWT}), 1.5), 25)))")},
    {"label": "BBB4_group_neutralize_inner",
     "logic": "group_neutralize inner signal first",
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply("
         f"group_neutralize({ACCEL1}, subindustry), {VOLWT}), 25)))")},
    {"label": "BBB5_reverse_inside",
     "logic": "reverse INSIDE: smooth(reversed_signal)",
     "expression": (
         f"zscore(ts_decay_linear(multiply(reverse({ACCEL1}), {VOLWT}), 25))")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r53_diff_skeletons_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "5 alphas with truly different skeletons.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/5] {v['label']}: {v['logic']}")
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
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R53 different skeletons\n\n"
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
        c_cell = "PASS" if conc_ok else f"FAIL({conc.get('value','?')})"
        s_cell = "PASS" if sub_ok else f"FAIL({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['logic']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {c_cell} | {s_cell} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
