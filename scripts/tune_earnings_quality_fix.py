"""Round 24: fix LOW_SUB_UNIVERSE_SHARPE on V3 earnings quality.

R23 found V3 (cashflow_op / income, LONG) is the first non-PV alpha
to pass CONCENTRATED_WEIGHT. Stats: SH=+0.67 TO=0.039 FIT=+0.43
conc=PASS  sub-uni=FAIL (-0.42 vs 0.29 cutoff).

Sub-universe SH being NEGATIVE means the alpha works on the full
universe but fails on a sub-slice (typically TOP500 or TOP1000).
The signal is concentrated in certain stocks where it works, but
collapses on others.

Fixes to try (4 sims):

  Y1  V3 with MARKET neut (broader cross-section)
  Y2  V3 with INDUSTRY neut (vs current SUBINDUSTRY)
  Y3  V3 with longer decay D=40 (more smoothing)
  Y4  V3 + asset_growth compound (stabilize via 2 fundamentals)

Settings: zscore wrapper, truncation=0.05, TOP3000, delay=1.
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
log = logging.getLogger("r24")

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

EARN_QUALITY = "divide(cashflow_op, income)"
ASSET_GROWTH = (
    "divide(subtract(assets, ts_delay(assets, 252)), ts_delay(assets, 252))"
)

VARIANTS = [
    {
        "label": "Y1_earnQ_MARKET",
        "fix": "MARKET neut (broader cross-section)",
        "neut": "MARKET",
        "expression": f"zscore(ts_decay_linear({EARN_QUALITY}, 20))",
    },
    {
        "label": "Y2_earnQ_INDUSTRY",
        "fix": "INDUSTRY neut (vs SUBINDUSTRY)",
        "neut": "INDUSTRY",
        "expression": f"zscore(ts_decay_linear({EARN_QUALITY}, 20))",
    },
    {
        "label": "Y3_earnQ_D40",
        "fix": "longer decay D=40 (more smoothing)",
        "neut": "SUBINDUSTRY",
        "expression": f"zscore(ts_decay_linear({EARN_QUALITY}, 40))",
    },
    {
        "label": "Y4_earnQ_minus_growth",
        "fix": "earnings_quality minus asset_growth (compound)",
        "neut": "SUBINDUSTRY",
        "expression": (
            f"zscore(ts_decay_linear(subtract({EARN_QUALITY}, {ASSET_GROWTH}), 20))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r24_earnQ_fix_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Fix LOW_SUB_UNIVERSE_SHARPE on V3 earnings_quality.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        settings = dict(BASE)
        settings["neutralization"] = v["neut"]
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  [neut={v['neut']}]")
        log.info(f"      fix:  {v['fix']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], settings)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "fix": v["fix"],
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
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} "
                             f"limit={chk.get('limit')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = f"# Round 24 - fix sub-universe Sharpe on V3 earnings_quality\n\n"
    md += f"## Results (ranked by SH)\n\n"
    md += f"| variant | fix | SH | TO | FIT | conc | sub-uni | checks |\n"
    md += f"|---|---|---:|---:|---:|---|---|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: r["sharpe"], reverse=True)
    survivors = []
    for r in ok_results:
        conc = next((c for c in r.get("checks", []) if c.get("name") == "CONCENTRATED_WEIGHT"), {})
        sub = next((c for c in r.get("checks", []) if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
        conc_ok = conc.get("result") == "PASS"
        sub_ok = sub.get("result") == "PASS"
        if conc_ok and sub_ok and r["sharpe"] > 0.5:
            survivors.append(r)
        conc_val = conc.get("value", "?")
        sub_val = sub.get("value", "?")
        conc_cell = "PASS" if conc_ok else f"FAIL ({conc_val})"
        sub_cell = "PASS" if sub_ok else f"FAIL ({sub_val})"
        md += (f"| {r['variant']} | {r['fix']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{conc_cell} | {sub_cell} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['fix']} | FAIL | - | - | - | - | - |\n")
    md += f"\n**Pass all checks + SH>0.5: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "earnQ_fix_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
