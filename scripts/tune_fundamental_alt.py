"""Round 14: fundamental + alternative-data factor families on USA TOP3000.

Diversifies away from price/volume-only signals (the prior 12 rounds
of work). Uses 5 distinct field categories to surface heterogeneous
alpha sources:

  F1 Value             -- bookvalue_ps / close (book-to-market) LONG
  F2 Quality           -- return_equity (ROE) LONG
  F3 Earnings revision -- snt1_d1_earningsrevision LONG (analyst category)
  F4 Low-vol anomaly   -- historical_volatility_60 REVERSED (option cat)
  F5 Target revision   -- snt1_d1_nettargetpercent LONG (sentiment cat)

Each is mechanically distinct from the existing 6 deliverable families
(close-close reversal, liqflow, intraday-volwt, price-acc, R^2 momentum
[dead], wrapper-neut variants).

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1, pasteurization=ON), but with nanHandling=ON for
sparser fundamental/alt-data fields.

Filter: SH>1.3, FIT>1.0, TO<0.2.
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
log = logging.getLogger("r14")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.3
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.2

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
        "label": "F1_value_btm",
        "family": "value",
        "field": "bookvalue_ps",
        "logic": "book-to-market LONG (cheap stocks outperform)",
        "expression": "zscore(ts_decay_linear(divide(bookvalue_ps, close), 20))",
    },
    {
        "label": "F2_quality_roe",
        "family": "quality",
        "field": "return_equity",
        "logic": "ROE LONG (high quality outperforms)",
        "expression": "zscore(ts_decay_linear(return_equity, 20))",
    },
    {
        "label": "F3_earnings_revision",
        "family": "earnings_momentum",
        "field": "snt1_d1_earningsrevision",
        "logic": "analyst earnings revision LONG (rising estimates carry)",
        "expression": "zscore(ts_decay_linear(snt1_d1_earningsrevision, 20))",
    },
    {
        "label": "F4_lowvol",
        "family": "low_vol_anomaly",
        "field": "historical_volatility_60",
        "logic": "60d historical vol REVERSED (low-vol anomaly)",
        "expression": "zscore(reverse(ts_decay_linear(historical_volatility_60, 20)))",
    },
    {
        "label": "F5_nettarget_revision",
        "family": "analyst_targets",
        "field": "snt1_d1_nettargetpercent",
        "logic": "net target-revision LONG (raised targets carry)",
        "expression": "zscore(ts_decay_linear(snt1_d1_nettargetpercent, 20))",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r14_fundamental_alt_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"5 fundamental + alternative-data factor families on USA TOP3000.\n"
        f"Categories: value, quality, earnings, option/low-vol, analyst.\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  [{v['family']}]")
        log.info(f"      field: {v['field']}")
        log.info(f"      logic: {v['logic']}")
        log.info(f"      expr:  {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "family": v["family"],
            "field": v["field"],
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
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = f"# Round 14 - fundamental + alternative-data factor families\n\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1, nanHandling=ON.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Results\n\n"
    md += f"| variant | family | field | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['family']} | `{r['field']}` | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['family']} | `{r['field']}` | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"

    families_covered = sorted({r["family"] for r in survivors})
    md += f"\n**Distinct families covered: {len(families_covered)}** ({', '.join(families_covered) if families_covered else 'none'})\n"
    (session_dir / "outputs" / "fundamental_alt_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 14 final - fundamental + alternative\n\n"
                f"Variants: {len(results)}\n"
                f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, "
                f"TO<{TURNOVER_CEILING}\n"
                f"Survivors: {len(survivors)}/{len(results)}\n"
                f"Distinct families covered: {len(families_covered)}\n")
    if survivors:
        survivors.sort(key=lambda r: r["sharpe"], reverse=True)
        summary += "\n## Survivors (ranked by SH, grouped by family)\n\n"
        by_fam = {}
        for r in survivors:
            by_fam.setdefault(r["family"], []).append(r)
        for fam, rs in by_fam.items():
            summary += f"### Family: {fam}\n\n"
            for r in rs:
                summary += (f"#### {r['variant']}\n"
                             f"- alpha_id: `{r['alpha_id']}`\n"
                             f"- field: `{r['field']}`\n"
                             f"- logic: {r['logic']}\n"
                             f"- expression: `{r['expression']}`\n"
                             f"- SH={r['sharpe']:+.3f}  TO={r['turnover']:.3f}  "
                             f"FIT={r['fitness']:+.3f}  RET={r['returns']:+.3f}  "
                             f"DD={r['drawdown']:.3f}\n"
                             f"- checks: {r['checks_passed']}/{r['checks_total']}\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(summary)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
