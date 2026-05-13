"""Round 52: extend ZZ3 vol-ratio*accel*volwt for 2+ more passing alphas.

R51/ZZ3 (E5q3xNZ9): vol_ratio(5,60) * accel(1) * volwt rev D=25
  SH=+1.93 TO=0.176 FIT=+2.63 ALL CHECKS PASS

5 sibling variants varying vol windows + accel + D:
  AAA1  vol_ratio(3, 60) * accel(1) * volwt rev D=25
  AAA2  vol_ratio(10, 60) * accel(1) * volwt rev D=25
  AAA3  vol_ratio(5, 120) * accel(1) * volwt rev D=25
  AAA4  vol_ratio(5, 60) * accel(2) * volwt rev D=25
  AAA5  vol_ratio(5, 60) * accel(1) * volwt rev D=30
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r52")
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


def expr(short_w: int, long_w: int, accel_w: int, d: int) -> str:
    ratio = f"divide(ts_std_dev(returns, {short_w}), ts_std_dev(returns, {long_w}))"
    accel = f"subtract(returns, ts_delay(returns, {accel_w}))"
    return f"zscore(reverse(ts_decay_linear(multiply(multiply({ratio}, {accel}), {VOLWT}), {d})))"


VARIANTS = [
    {"label": "AAA1_s3_l60_a1_D25", "params": (3, 60, 1, 25)},
    {"label": "AAA2_s10_l60_a1_D25", "params": (10, 60, 1, 25)},
    {"label": "AAA3_s5_l120_a1_D25", "params": (5, 120, 1, 25)},
    {"label": "AAA4_s5_l60_a2_D25", "params": (5, 60, 2, 25)},
    {"label": "AAA5_s5_l60_a1_D30", "params": (5, 60, 1, 30)},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r52_zz3_extensions_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text("Extend ZZ3 vol-ratio family.\n")
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        s, l, a, d = v["params"]
        expression = expr(s, l, a, d)
        log.info(f"  [{i}/5] {v['label']}: s={s} l={l} a={a} D={d}")
        log.info(f"      expr: {expression}")
        try:
            res = r5.submit(cm.session, expression, BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "short_w": s, "long_w": l,
                 "accel_w": a, "d": d, "expression": expression, **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R52 ZZ3 extensions\n\n"
    md += ("| variant | s | l | a | D | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|\n")
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
        c_cell = "P" if conc_ok else f"F({conc.get('value','?')})"
        s_cell = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['short_w']} | {r['long_w']} | "
                f"{r['accel_w']} | {r['d']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {c_cell} | {s_cell} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | - | - | - | - | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
