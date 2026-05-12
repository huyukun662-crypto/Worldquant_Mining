"""Round 27: extend AA4 snt_social_value -- first WQ-compliant non-PV alpha.

R26 found AA4 (snt_social_value LONG, D=20, SUBINDUSTRY) passes BOTH
CONCENTRATED_WEIGHT AND LOW_SUB_UNIVERSE_SHARPE -- the first non-PV
alpha in 9 rounds (R17-R26) to clear all checks. But SH=0.34 is low.

R27 sweeps to boost SH while maintaining checks:

  BB1  snt_social_value LONG, D=40 (more smoothing)
  BB2  snt_social_value LONG, D=10 (less smoothing, may up SH)
  BB3  snt_social_volume LONG (alt sentiment field)
  BB4  compound: snt_social_value + snt_social_volume (additive)
  BB5  ts_zscore(snt_social_value, 60) -- normalized change

Same proven settings (zscore wrapper, SUBINDUSTRY neut, truncation=0.05,
decay=8, TOP3000, delay=1, nanHandling=ON).
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
log = logging.getLogger("r27")

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

VARIANTS = [
    {
        "label": "BB1_social_value_D40",
        "logic": "snt_social_value LONG D=40 (more smoothing)",
        "expression": "zscore(ts_decay_linear(snt_social_value, 40))",
    },
    {
        "label": "BB2_social_value_D10",
        "logic": "snt_social_value LONG D=10 (less smoothing)",
        "expression": "zscore(ts_decay_linear(snt_social_value, 10))",
    },
    {
        "label": "BB3_social_volume_long",
        "logic": "snt_social_volume LONG (alt sentiment field)",
        "expression": "zscore(ts_decay_linear(snt_social_volume, 20))",
    },
    {
        "label": "BB4_compound_value_plus_volume",
        "logic": "snt_social_value + snt_social_volume compound",
        "expression": (
            "zscore(ts_decay_linear(add(snt_social_value, snt_social_volume), 20))"
        ),
    },
    {
        "label": "BB5_ts_zscore_social_value",
        "logic": "60d ts_zscore of snt_social_value LONG",
        "expression": (
            "zscore(ts_decay_linear(ts_zscore(snt_social_value, 60), 20))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r27_sentiment_extensions_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Extend AA4 social-sentiment alpha (only WQ-compliant non-PV so far).\n"
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

    md = f"# Round 27 - extend AA4 social-sentiment alpha\n\n"
    md += f"Reference: AA4 (snt_social_value LONG D=20): SH=+0.340 conc=PASS sub=PASS 0.45\n\n"
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
        if conc_ok and sub_ok and r["sharpe"] > 0.2:
            survivors.append(r)
        conc_val = conc.get("value", "?")
        sub_val = sub.get("value", "?")
        conc_cell = "PASS" if conc_ok else f"FAIL ({conc_val})"
        sub_cell = "PASS" if sub_ok else f"FAIL ({sub_val})"
        md += (f"| {r['variant']} | {r['logic']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{conc_cell} | {sub_cell} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | - |\n")
    md += f"\n**Pass all checks + SH>0.2: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "sentiment_extensions_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
