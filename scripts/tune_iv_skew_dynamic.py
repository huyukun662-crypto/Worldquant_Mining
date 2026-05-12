"""Round 22: time-series transformations of IV skew (dynamic signals).

R20/R21 established: raw IV skew level fails CONCENTRATED_WEIGHT and
LOW_SUB_UNIVERSE_SHARPE no matter how we tune wrapper/neut/truncation/
winsorize/universe. Root cause: option IV is sparse cross-sectionally
on some dates -- a handful of stocks dominate weight.

R22 pivots to DYNAMIC IV signals -- relative to each stock's own
history. These only need SEQUENTIAL observations (not absolute levels
across all stocks), giving them wider cross-sectional coverage:

  U1  ts_zscore(SKEW_180, 60) REVERSED
       -- 60d time-series zscore of IV skew, reversed
       -- captures stocks where current IV skew is unusually high vs own history
  U2  ts_zscore(SKEW_30,  60) REVERSED
       -- same but short-tenor
  U3  subtract(SKEW_180, ts_mean(SKEW_180, 60)) REVERSED
       -- deviation from 60d mean of own skew
  U4  ts_zscore(SKEW_180, 20) REVERSED
       -- short-window dynamic
  U5  divide(SKEW_180, ts_std_dev(SKEW_180, 60)) REVERSED
       -- skew normalized by own vol of skew

Settings: zscore wrapper, SUBINDUSTRY neut (R20 proved SUBINDUSTRY
halves concentration), truncation=0.05, TOP3000, delay=1.

Target: pass BOTH CONCENTRATED_WEIGHT and LOW_SUB_UNIVERSE_SHARPE
while maintaining SH > 1.25.
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
log = logging.getLogger("r22")

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
SKEW_30 = "subtract(implied_volatility_put_30, implied_volatility_call_30)"

VARIANTS = [
    {
        "label": "U1_skew180_ts_zscore_60",
        "logic": "60d ts_zscore of 180-tenor IV skew, REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear(ts_zscore({SKEW_180}, 60), 20)))"
        ),
    },
    {
        "label": "U2_skew30_ts_zscore_60",
        "logic": "60d ts_zscore of 30-tenor IV skew, REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear(ts_zscore({SKEW_30}, 60), 20)))"
        ),
    },
    {
        "label": "U3_skew180_minus_mean60",
        "logic": "180-tenor skew minus its 60d mean, REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear("
            f"subtract({SKEW_180}, ts_mean({SKEW_180}, 60)), 20)))"
        ),
    },
    {
        "label": "U4_skew180_ts_zscore_20",
        "logic": "20d ts_zscore of 180-tenor IV skew, REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear(ts_zscore({SKEW_180}, 20), 20)))"
        ),
    },
    {
        "label": "U5_skew180_normalized",
        "logic": "180-tenor skew / its 60d std, REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear("
            f"divide({SKEW_180}, ts_std_dev({SKEW_180}, 60)), 20)))"
        ),
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r22_iv_skew_dynamic_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Dynamic IV skew (ts_zscore / dev from mean) to fix data sparsity.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      logic: {v['logic']}")
        log.info(f"      expr:  {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "logic": v["logic"],
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

    md = f"# Round 22 - dynamic IV skew (time-series transformations)\n\n"
    md += f"## Results (ranked by SH)\n\n"
    md += f"| variant | logic | SH | TO | FIT | conc | sub-uni | checks |\n"
    md += f"|---|---|---:|---:|---:|---|---|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: r["sharpe"], reverse=True)
    survivors = []
    for r in ok_results:
        conc = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
        sub = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
        conc_ok = conc.get("result") == "PASS"
        sub_ok = sub.get("result") == "PASS"
        if conc_ok and sub_ok and r["sharpe"] > 1.25 and r["turnover"] < 0.25:
            survivors.append(r)
        conc_cell = "PASS" if conc_ok else f"FAIL ({conc.get('value', '?')})"
        sub_cell = "PASS" if sub_ok else f"FAIL ({sub.get('value', '?')})"
        md += (f"| {r['variant']} | {r['logic']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{conc_cell} | {sub_cell} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | - |\n")
    md += f"\n**Survivors (all checks passed): {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "iv_skew_dynamic_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
