"""Round 19: extend the option-IV skew family.

R18/Q1 found: zscore(reverse(ts_decay_linear(subtract(put_30, call_30), 20)))
gave SH=+1.650 TO=0.227 FIT=+1.810 on USA TOP3000 INDUSTRY.

This is the only non-PV alpha discovered so far that clears
SH>1.25 ∩ TO<0.25 ∩ FIT>1.0. R19 mines siblings to deliver 2 more:

  R1 IV skew rev, decay 10  -- shorter, higher SH (likely higher TO)
  R2 IV skew rev, decay 30  -- more smoothing, may pull TO under 0.20
  R3 IV skew (180-tenor), decay 20  -- longer-dated options for stability
  R4 compound: IV skew * hist_vol_20  -- vol-weighted by historical vol
  R5 Q4 retry (asset_growth MARKET neut)
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
log = logging.getLogger("r19")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 8,
    "truncation": 0.08,
    "neutralization": "INDUSTRY",
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

SKEW_30 = "subtract(implied_volatility_put_30, implied_volatility_call_30)"
SKEW_180 = "subtract(implied_volatility_put_180, implied_volatility_call_180)"
ASSET_GROWTH = (
    "divide(subtract(assets, ts_delay(assets, 252)), ts_delay(assets, 252))"
)

VARIANTS = [
    {
        "label": "R1_iv_skew30_rev_D10",
        "neut": "INDUSTRY",
        "expression": f"zscore(reverse(ts_decay_linear({SKEW_30}, 10)))",
    },
    {
        "label": "R2_iv_skew30_rev_D30",
        "neut": "INDUSTRY",
        "expression": f"zscore(reverse(ts_decay_linear({SKEW_30}, 30)))",
    },
    {
        "label": "R3_iv_skew180_rev_D20",
        "neut": "INDUSTRY",
        "expression": f"zscore(reverse(ts_decay_linear({SKEW_180}, 20)))",
    },
    {
        "label": "R4_iv_skew_volwt",
        "neut": "INDUSTRY",
        "expression": (
            f"zscore(reverse(ts_decay_linear("
            f"multiply({SKEW_30}, historical_volatility_20), 20)))"
        ),
    },
    {
        "label": "R5_asset_growth_MARKET_retry",
        "neut": "MARKET",
        "expression": f"zscore(reverse(ts_decay_linear({ASSET_GROWTH}, 20)))",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r19_iv_skew_family_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Extend IV skew family + retry asset_growth MARKET.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        settings = dict(BASE)
        settings["neutralization"] = v["neut"]
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  [neut={v['neut']}]")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], settings)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "neut": v["neut"],
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
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = f"# Round 19 - extend IV skew family\n\n"
    md += f"Reference: R18/Q1 (iv_skew_30 rev D=20): SH=+1.650 TO=0.227 FIT=+1.810\n\n"
    md += f"## Results (ranked by |SH|)\n\n"
    md += f"| variant | neut | SH | TO | FIT | RET | DD | checks |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    for r in ok_results:
        md += (f"| {r['variant']} | {r['neut']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['neut']} | FAIL | - | - | - | - | - |\n")
    (session_dir / "outputs" / "iv_skew_family_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
