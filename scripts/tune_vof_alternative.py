"""Round 45: try non-std_dev volume signals to fix CONCENTRATED_WEIGHT.

R44 confirmed: truncation cap doesn't enforce per-stock weight (same
issue as R20-R21 IV skew). The vol-of-vol (ts_std_dev) generates
cross-sectional outliers on sparse-volume days, driving 30%+ concentration.

Replace ts_std_dev(vol/adv20) with denser/smoother proxies:

  UU1  winsorize(vof, std=3) * accel * volwt  -- cap outliers in vof
  UU2  ts_mean(vol/adv20, 20) * accel * volwt -- use mean (denser) not std
  UU3  divide(vol, ts_mean(vol, 60)) * accel * volwt -- vol level ratio
  UU4  ts_std_dev(returns, 20) * accel * volwt -- realized return vol
  UU5  ts_quantile(vol/adv20, 0.9, 20) * accel * volwt -- 90th percentile vol

Target: SH>=1.75, TO<0.20, FIT>1.25, CONC<0.10.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r45")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.05, "neutralization": "INDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

ACCEL = "subtract(returns, ts_delay(returns, 2))"
VOLWT = "log(add(divide(volume, adv20), 1))"


def wrap(driver: str) -> str:
    return (f"zscore(reverse(ts_decay_linear(multiply(multiply("
            f"{driver}, {ACCEL}), {VOLWT}), 30)))")


VARIANTS = [
    {"label": "UU1_winsorize_vof",
     "driver": "winsorize(ts_std_dev(divide(volume, adv20), 25), std=3)",
     "logic": "winsorize vof at std=3"},
    {"label": "UU2_ts_mean_vol",
     "driver": "ts_mean(divide(volume, adv20), 20)",
     "logic": "use ts_mean(vol/adv20) -- denser than std_dev"},
    {"label": "UU3_vol_level_ratio",
     "driver": "divide(volume, ts_mean(volume, 60))",
     "logic": "current vol / 60d mean vol level"},
    {"label": "UU4_realized_retvol",
     "driver": "ts_std_dev(returns, 20)",
     "logic": "realized return vol (denser than vol-of-vol)"},
    {"label": "UU5_vol_quantile",
     "driver": "ts_quantile(divide(volume, adv20), 0.9, 20)",
     "logic": "ts_quantile 0.9 of vol/adv20 -- top decile vol"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r45_vof_alternative_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Replace ts_std_dev(vol/adv20) with denser volume proxies to fix CONC.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        expression = wrap(v["driver"])
        log.info(f"  [{i}/5] {v['label']}: {v['logic']}")
        log.info(f"      expr: {expression}")
        try:
            res = r5.submit(cm.session, expression, BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "logic": v["logic"],
                 "driver": v["driver"], "expression": expression, **res}
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
    md = "# R45 vof alternatives\n\n"
    md += ("| variant | logic | SH | TO | FIT | conc | passes? |\n"
           "|---|---|---:|---:|---:|---|---|\n")
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
        md += (f"| {r['variant']} | {r['logic']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {conc_cell} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
