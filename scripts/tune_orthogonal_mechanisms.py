"""Round 8: 3 mechanistically distinct alphas to avoid correlation with the
reversal family from R5/R6/R7.

The 10 prior survivors all share the spine:
  <wrapper>(reverse(ts_decay_linear(multiply(ts_zscore(returns, W),
            log(add(divide(volume, adv20), 1))), D)))
i.e. short-term mean reversion in residual returns, weighted by abnormal
volume. To diversify, we change BOTH the input field AND the structure:

  Mechanism A -- intraday range cross-sectional reversion
    Driver: (high - low)/close  (realized intraday vol, NEW field)
    Logic:  cross-sectionally high realized vol mean-reverts
    Two windows tested (N1a, N1b).

  Mechanism B -- overnight gap mean reversion
    Driver: (open - ts_delay(close, 1))/ts_delay(close, 1)  (overnight return)
    Logic:  overnight gaps fade in the next session
    Two outer-decay choices tested (N2a, N2b).

  Mechanism C -- liquidity-flow momentum (no reverse)
    Driver: 20d change in adv20 (relative volume trend)
    Logic:  stocks gaining attention/liquidity LONG winners
    Single configuration (N3).

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1, pasteurization=ON).

Filter for delivery: SH > 1.35  AND  FIT > 1.0  AND  TO < 0.15.
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
log = logging.getLogger("r8")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 1.35
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.15

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
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VARIANTS = [
    {
        "label": "N1a_range_zwin20_D20",
        "mechanism": "intraday range compression",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "ts_zscore(divide(subtract(high, low), close), 20), 20)))"
        ),
        "notes": "high-low/close, 20d cross-sectional zscore, 20d outer decay",
    },
    {
        "label": "N1b_range_zwin5_D30",
        "mechanism": "intraday range compression",
        "expression": (
            "zscore(reverse(ts_decay_linear("
            "ts_zscore(divide(subtract(high, low), close), 5), 30)))"
        ),
        "notes": "high-low/close, 5d zscore (shorter window), 30d outer decay",
    },
    {
        "label": "N2a_overnight_D5",
        "mechanism": "overnight gap mean reversion",
        "expression": (
            "zscore(reverse(ts_decay_linear(divide(subtract(open, "
            "ts_delay(close, 1)), ts_delay(close, 1)), 5)))"
        ),
        "notes": "overnight return, very short 5d decay (gap is 1-3 day phenom)",
    },
    {
        "label": "N2b_overnight_D20",
        "mechanism": "overnight gap mean reversion",
        "expression": (
            "zscore(reverse(ts_decay_linear(divide(subtract(open, "
            "ts_delay(close, 1)), ts_delay(close, 1)), 20)))"
        ),
        "notes": "overnight return, 20d decay (smoothed across gaps)",
    },
    {
        "label": "N3_liqflow_D10",
        "mechanism": "liquidity flow momentum",
        "expression": (
            "zscore(ts_decay_linear(divide(subtract(adv20, "
            "ts_delay(adv20, 20)), ts_delay(adv20, 20)), 10))"
        ),
        "notes": "20d change in adv20, LONG winners (no reverse), 10d decay",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_diversification_r8_orthogonal_mechanisms_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Deliver 3 alphas with mechanisms distinct from the reversal family.\n"
        f"3 mechanisms x 5 variants tested.\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  [{v['mechanism']}]")
        log.info(f"      {v['notes']}")
        log.info(f"      expr: {v['expression']}")
        res = r5.submit(cm.session, v["expression"], BASE)
        entry = {
            "variant": v["label"],
            "mechanism": v["mechanism"],
            "notes": v["notes"],
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

    md = f"# Round 8 - orthogonal-mechanism sweep\n\n"
    md += f"3 mechanisms (intraday range, overnight gap, liquidity flow), 5 variants.\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Results\n\n"
    md += f"| variant | mechanism | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['mechanism']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['mechanism']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "orthogonal_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 8 final - orthogonal mechanisms\n\n"
                f"Variants: {len(results)}  (3 mechanisms)\n"
                f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, "
                f"TO<{TURNOVER_CEILING}\n"
                f"Survivors: {len(survivors)}/{len(results)}\n")
    if survivors:
        survivors.sort(key=lambda r: r["sharpe"], reverse=True)
        summary += "\n## Survivors (ranked by SH)\n\n"
        for r in survivors:
            summary += (f"### {r['variant']}  ({r['mechanism']})\n"
                         f"- alpha_id: `{r['alpha_id']}`\n"
                         f"- expression: `{r['expression']}`\n"
                         f"- notes: {r['notes']}\n"
                         f"- SH={r['sharpe']:+.3f}  TO={r['turnover']:.3f}  "
                         f"FIT={r['fitness']:+.3f}  RET={r['returns']:+.3f}  "
                         f"DD={r['drawdown']:.3f}\n"
                         f"- checks: {r['checks_passed']}/{r['checks_total']}\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(summary)
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
