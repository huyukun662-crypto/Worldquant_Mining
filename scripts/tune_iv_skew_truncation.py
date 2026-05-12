"""Round 21: aggressive truncation + winsorize on IV skew.

R20 showed:
  - SUBINDUSTRY reduced concentration from 50% -> 15% (better but not <10%)
  - quantile() didn't help (still 16-17%)
  - All 5 R20 variants failed CONCENTRATED_WEIGHT and SUB_UNIVERSE_SHARPE

Concentration ~15-17% is consistent across wrapper/neut choices because
option IV is naturally sparse (only ~85% of TOP3000 have liquid options).
The only direct fix is the truncation parameter (per-stock weight cap).

R21 grid (5 sims, all on R3 = 180-tenor IV skew, which has the highest
raw SH=2.23):

  T1 truncation=0.05, SUBINDUSTRY
  T2 truncation=0.03, SUBINDUSTRY  -- aggressive
  T3 truncation=0.02, SUBINDUSTRY  -- very aggressive
  T4 winsorize(zscore(...), std=2) cap z-scores at +-2 stds
  T5 truncation=0.03 + SUBINDUSTRY + universe=TOP1000 (more options-liquid)

zscore wrapper kept (R20/S2 showed zscore + SUBINDUSTRY preserved SH best).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r21")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 8,
    "truncation": 0.05,
    "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

SKEW_180 = "subtract(implied_volatility_put_180, implied_volatility_call_180)"
CORE_180 = f"reverse(ts_decay_linear({SKEW_180}, 20))"

VARIANTS = [
    {
        "label": "T1_trunc05_SUBIN",
        "fix": "truncation=0.05 + SUBINDUSTRY",
        "settings_overrides": {"truncation": 0.05, "neutralization": "SUBINDUSTRY"},
        "expression": f"zscore({CORE_180})",
    },
    {
        "label": "T2_trunc03_SUBIN",
        "fix": "truncation=0.03 + SUBINDUSTRY (aggressive)",
        "settings_overrides": {"truncation": 0.03, "neutralization": "SUBINDUSTRY"},
        "expression": f"zscore({CORE_180})",
    },
    {
        "label": "T3_trunc02_SUBIN",
        "fix": "truncation=0.02 + SUBINDUSTRY (very aggressive)",
        "settings_overrides": {"truncation": 0.02, "neutralization": "SUBINDUSTRY"},
        "expression": f"zscore({CORE_180})",
    },
    {
        "label": "T4_winsorize_std2",
        "fix": "winsorize(zscore(.), std=2) -- explicit bound",
        "settings_overrides": {"truncation": 0.05, "neutralization": "SUBINDUSTRY"},
        "expression": f"winsorize(zscore({CORE_180}), std=2)",
    },
    {
        "label": "T5_trunc03_TOP1000",
        "fix": "truncation=0.03 + SUBINDUSTRY + universe=TOP1000",
        "settings_overrides": {
            "truncation": 0.03, "neutralization": "SUBINDUSTRY",
            "universe": "TOP1000",
        },
        "expression": f"zscore({CORE_180})",
    },
]


def _load(p: Path, name: str):
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r21_iv_skew_truncation_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Aggressive truncation + winsorize on R3 (180-tenor IV skew).\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        settings = dict(BASE)
        settings.update(v["settings_overrides"])
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      fix: {v['fix']}")
        log.info(f"      settings: trunc={settings['truncation']} "
                 f"neut={settings['neutralization']} universe={settings['universe']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], settings)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "fix": v["fix"],
            "settings_overrides": v["settings_overrides"],
            "expression": v["expression"],
            **res,
        }
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} RET={res['returns']:+.3f} "
                     f"checks={res['checks_passed']}/{res['checks_total']}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} "
                             f"limit={chk.get('limit')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = f"# Round 21 - aggressive truncation + winsorize on IV skew\n\n"
    md += f"## Results (ranked by SH, only ok)\n\n"
    md += f"| variant | fix | SH | TO | FIT | conc_pass? | subuni_pass? | checks |\n"
    md += f"|---|---|---:|---:|---:|---|---|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: r["sharpe"], reverse=True)
    survivors = []
    for r in ok_results:
        conc_check = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
        sub_check = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
        conc_ok = conc_check.get("result") == "PASS"
        sub_ok = sub_check.get("result") == "PASS"
        if conc_ok and sub_ok and r["sharpe"] > 1.25 and r["turnover"] < 0.25:
            survivors.append(r)
        md += (f"| {r['variant']} | {r['fix']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{'YES' if conc_ok else f'FAIL ({conc_check.get(\"value\", \"?\")})'} | "
                f"{'YES' if sub_ok else f'FAIL ({sub_check.get(\"value\", \"?\")})'} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['fix']} | FAIL | - | - | - | - | - |\n")
    md += f"\n**Survivors clearing all checks + SH>1.25 + TO<0.25: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "iv_skew_truncation_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
