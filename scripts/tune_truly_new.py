"""Round 51: 5 truly new structural families.

Avoiding all 8 existing PV families (R5-R48). 5 fresh structures:

  ZZ1  multi-tenor reversal DIFFERENTIAL (subtraction not multiply):
       subtract(ts_zscore(returns, 5), ts_zscore(returns, 20)) * volwt rev
  ZZ2  NESTED ts_zscore (time-series of time-series):
       ts_zscore(ts_zscore(returns, 5), 20) * volwt rev
  ZZ3  short/long vol RATIO x accel x volwt:
       divide(ts_std_dev(returns,5), ts_std_dev(returns,60)) x accel x volwt rev
  ZZ4  pure CROSS-SECTIONAL rank difference (no decay/no reverse):
       subtract(rank(ts_zscore(returns,5)), rank(divide(volume,adv20)))
  ZZ5  sign-magnitude DECOMPOSITION x volwt rev:
       multiply(sign(returns), abs(subtract(returns, ts_delay(returns,1)))) * volwt rev

Settings: USA TOP3000 delay=1 SUBINDUSTRY decay=8 trunc=0.05 past=ON nan=OFF.
Filter: SH>=1.75, TO<0.20, FIT>1.25, all WQ checks PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r51")
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

VARIANTS = [
    {"label": "ZZ1_revdiff_5m20",
     "logic": "differential: ts_zscore(returns,5)-ts_zscore(returns,20) x volwt rev",
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply(subtract("
         f"ts_zscore(returns, 5), ts_zscore(returns, 20)), {VOLWT}), 20)))")},
    {"label": "ZZ2_nested_zscore",
     "logic": "ts_zscore(ts_zscore(returns,5),20) x volwt rev",
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply("
         f"ts_zscore(ts_zscore(returns, 5), 20), {VOLWT}), 25)))")},
    {"label": "ZZ3_vol_ratio_accel",
     "logic": "ts_std_dev(ret,5)/ts_std_dev(ret,60) x accel x volwt rev",
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply(multiply("
         f"divide(ts_std_dev(returns,5), ts_std_dev(returns,60)), "
         f"{ACCEL1}), {VOLWT}), 25)))")},
    {"label": "ZZ4_xs_rank_diff",
     "logic": "rank(ts_zscore(returns,5)) - rank(volume/adv20) -- pure XS",
     "expression": (
         f"zscore(subtract(rank(ts_zscore(returns, 5)), "
         f"rank(divide(volume, adv20))))")},
    {"label": "ZZ5_sign_mag_decomp",
     "logic": "sign(returns) x abs(accel) x volwt rev",
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply(multiply("
         f"sign(returns), abs({ACCEL1})), {VOLWT}), 25)))")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r51_truly_new_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "5 truly new structural families (differential/nested/ratio/XS/decomp).\n"
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
    md = "# R51 truly new structures\n\n"
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
