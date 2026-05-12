"""Round 18: option-implied + sentiment + cross-neut fundamentals.

R17 showed classic fundamentals are weak under INDUSTRY neut on
TOP3000. R18 explores:
  Q1 Option IV skew (put_30 - call_30) REVERSED
        -- high put IV / low call IV = fear -> reverse to LONG low-fear
  Q2 Option IV term structure (call_30 - call_180) REVERSED
        -- inverted term structure = stress -> reverse to LONG normal-curve
  Q3 Social-media sentiment z-score LONG (snt_social_value)
        -- positive social sentiment -> LONG
  Q4 P5 (asset growth REV) with MARKET neut (vs R17 INDUSTRY)
        -- restore cross-sector growth premium
  Q5 Compound: asset growth + gross profitability (quality-growth blend)
        -- (revenue-cogs)/assets minus 252d-asset-growth, smoothed

Same proven settings (zscore wrapper, decay=8, trunc=0.08, TOP3000,
delay=1, nanHandling=ON). Filter for triage: any |SH| > 0.7 noted.
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
log = logging.getLogger("r18")

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

VARIANTS = [
    {
        "label": "Q1_iv_skew_rev",
        "category": "option",
        "neut": "INDUSTRY",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "subtract(implied_volatility_put_30, implied_volatility_call_30), 20)))"
        ),
    },
    {
        "label": "Q2_iv_term_rev",
        "category": "option",
        "neut": "INDUSTRY",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "subtract(implied_volatility_call_30, implied_volatility_call_180), 20)))"
        ),
    },
    {
        "label": "Q3_social_sent_long",
        "category": "socialmedia",
        "neut": "INDUSTRY",
        "expression": (
            "zscore(ts_decay_linear(snt_social_value, 20))"
        ),
    },
    {
        "label": "Q4_asset_growth_MARKET",
        "category": "fundamental",
        "neut": "MARKET",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "divide(subtract(assets, ts_delay(assets, 252)), "
            "ts_delay(assets, 252)), 20)))"
        ),
    },
    {
        "label": "Q5_gp_minus_growth",
        "category": "fundamental",
        "neut": "INDUSTRY",
        "expression": (
            "zscore(ts_decay_linear(subtract("
            "divide(subtract(revenue, cogs), assets), "
            "divide(subtract(assets, ts_delay(assets, 252)), "
            "ts_delay(assets, 252))), 20))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r18_option_sent_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Option IV skew/term + sentiment + cross-neut fundamentals.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        settings = dict(BASE)
        settings["neutralization"] = v["neut"]
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  [{v['category']}, neut={v['neut']}]")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], settings)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "category": v["category"],
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

    md = f"# Round 18 - option + sentiment + cross-neut fundamentals\n\n"
    md += f"## Results (ranked by |SH|)\n\n"
    md += f"| variant | category | neut | SH | TO | FIT | RET | DD | checks |\n"
    md += f"|---|---|---|---:|---:|---:|---:|---:|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    for r in ok_results:
        md += (f"| {r['variant']} | {r['category']} | {r['neut']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['category']} | {r['neut']} | FAIL | - | - | - | - | - |\n")
    (session_dir / "outputs" / "option_sentiment_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
