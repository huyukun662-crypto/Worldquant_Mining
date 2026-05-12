"""Round 10: vol-weight the corr/arg_min raw signals.

R9 showed:
  S1 corr(returns, vol/adv20, 20), reversed:   SH=+0.62
  S3 ts_arg_min(close, 60), reversed:          SH=+0.34
  S4 corr(close, volume, 20), LONG:            SH=-0.89 (flipped: +0.89)

Raw magnitudes are too weak (< 1.0) to clear SH>1.3. The vol-weight
amplification trick lifted intraday SH from 1.45 to 1.67 in R8e.
Applying it here:

  T1  corr(returns, vol/adv20) * vol_weight, REVERSED, D=20
  T2  corr(close, volume) * vol_weight, REVERSED, D=20  (S4 flipped + amp)
  T3  ts_arg_min(close, 60) * vol_weight, REVERSED, D=20
  T4  ts_arg_max(close, 60) * vol_weight, REVERSED, D=20  (new operator probe;
       may fail with G1 if ts_arg_max is blocked like ts_max)

If any survive, they are structurally distinct from the 3 deliverables:
  - Use ts_corr or ts_arg_min/max (operators not in the 3 deliverables)
  - Different logic: rolling correlation / time-since-extreme

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1). Filter: SH>1.3, FIT>1.0, TO<0.2.
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
log = logging.getLogger("r10")

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

VARIANTS = [
    {
        "label": "T1_corr_ret_volwt_rev",
        "logic": "return-vol corr reversal, vol-weighted",
        "structure": "ts_corr * vol_weight, reversed, smoothed",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_corr(returns, divide(volume, adv20), 20), {VOLWEIGHT}), 20)))"
        ),
    },
    {
        "label": "T2_corr_close_volwt_rev",
        "logic": "close-volume corr reversal, vol-weighted",
        "structure": "ts_corr(close, volume) * vol_weight, reversed",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_corr(close, volume, 20), {VOLWEIGHT}), 20)))"
        ),
    },
    {
        "label": "T3_argmin_volwt_rev",
        "logic": "days-since-60d-low reversal, vol-weighted",
        "structure": "ts_arg_min * vol_weight, reversed",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_arg_min(close, 60), {VOLWEIGHT}), 20)))"
        ),
    },
    {
        "label": "T4_argmax_volwt_rev",
        "logic": "days-since-60d-high reversal, vol-weighted (probe)",
        "structure": "ts_arg_max * vol_weight, reversed (new operator)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"ts_arg_max(close, 60), {VOLWEIGHT}), 20)))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_diversification_r10_volwt_corr_argmin_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Vol-weight the corr/arg_min signals to push SH above 1.3.\n"
        f"Same amplification trick that lifted intraday from 1.45 to 1.67 in R8e.\n"
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

    md = f"# Round 10 - vol-weighted corr/argmin\n\n"
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
    (session_dir / "outputs" / "volwt_corr_argmin_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 10 final - vol-weighted corr/argmin\n\n"
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
