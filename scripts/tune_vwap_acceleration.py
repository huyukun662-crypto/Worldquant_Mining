"""Round 11: vwap-based and price-acceleration signals.

R9/R10 confirmed corr/arg-extreme operators don't carry enough alpha
on this universe. R11 pivots to two genuinely untested mechanism
families:

  Family VWAP: stocks far from rolling VWAP mean-revert
    U1  (close - vwap) / vwap, REVERSED, D=20
    U2  (close - vwap) / vwap, vol-weighted, REVERSED, D=20

  Family ACC (price acceleration -- second time-derivative):
    U3  return change (returns - prev returns), REVERSED, D=20
    U4  range-position acceleration, vol-weighted, D=20
        (today's range_position - yesterday's), reversed

Structure novelty:
  - U1/U2: use the `vwap` field (not used in any of the 3 deliverables)
  - U3:    second-difference operator structure (subtract today's
           returns minus yesterday's via ts_delay) -- pure 2nd
           derivative of price
  - U4:    derivative of position-in-range, with vol-weight

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1). Filter: SH>1.3, FIT>1.0, TO<0.2.

NOTE: if `vwap` is not exposed on this account tier, U1/U2 fail with
a data-field error -- accept and continue.
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
log = logging.getLogger("r11")

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
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VOLWEIGHT = "log(add(divide(volume, adv20), 1))"
VWAP_DEV = "divide(subtract(close, vwap), vwap)"
RET_ACC = "subtract(returns, ts_delay(returns, 1))"
RANGE_POS = "divide(subtract(close, low), subtract(high, low))"

VARIANTS = [
    {
        "label": "U1_vwap_dev_rev",
        "logic": "close-vs-VWAP reversion",
        "structure": "(close-vwap)/vwap REVERSED, smoothed",
        "expression": (
            f"zscore(reverse(ts_decay_linear({VWAP_DEV}, 20)))"
        ),
    },
    {
        "label": "U2_vwap_dev_volwt_rev",
        "logic": "vol-weighted close-vs-VWAP reversion",
        "structure": "(close-vwap)/vwap * vol_weight REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"{VWAP_DEV}, {VOLWEIGHT}), 20)))"
        ),
    },
    {
        "label": "U3_price_acc_rev",
        "logic": "price acceleration reversal (2nd derivative)",
        "structure": "(returns - prev_returns) REVERSED, smoothed",
        "expression": (
            f"zscore(reverse(ts_decay_linear({RET_ACC}, 20)))"
        ),
    },
    {
        "label": "U4_range_pos_acc_volwt_rev",
        "logic": "range-position acceleration, vol-weighted, reversed",
        "structure": "(range_pos[t] - range_pos[t-1]) * vol_weight REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"subtract({RANGE_POS}, ts_delay({RANGE_POS}, 1)), {VOLWEIGHT}), 20)))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_diversification_r11_vwap_accel_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"vwap + price-acceleration mechanisms; new fields/structures.\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      logic:     {v['logic']}")
        log.info(f"      structure: {v['structure']}")
        log.info(f"      expr:      {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            log.warning(f"      EXCEPTION: {type(e).__name__}: {str(e)[:120]}")
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {
            "variant": v["label"],
            "logic": v["logic"],
            "structure": v["structure"],
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

    md = f"# Round 11 - vwap + price-acceleration\n\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Results\n\n"
    md += f"| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['logic']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['logic']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "vwap_accel_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 11 final - vwap + price-acceleration\n\n"
                f"Variants: {len(results)}\n"
                f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, "
                f"TO<{TURNOVER_CEILING}\n"
                f"Survivors: {len(survivors)}/{len(results)}\n")
    if survivors:
        survivors.sort(key=lambda r: r["sharpe"], reverse=True)
        summary += "\n## Survivors (ranked by SH)\n\n"
        for r in survivors:
            summary += (f"### {r['variant']}\n"
                         f"- alpha_id: `{r['alpha_id']}`\n"
                         f"- logic: {r['logic']}\n"
                         f"- structure: {r['structure']}\n"
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
