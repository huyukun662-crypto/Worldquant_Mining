"""Round 8b: convert R8 lessons into 3 mechanism-distinct survivors.

R8 result: only N3 (liquidity-flow momentum) had a strong magnitude,
but with the WRONG sign -- SH=-1.530, FIT=-2.030, TO=0.131. The
sign-flipped version (add `reverse`) is the discovery:
  zscore(reverse(ts_decay_linear(divide(subtract(adv20,
         ts_delay(adv20, 20)), ts_delay(adv20, 20)), 10)))
  expected: SH=+1.530, FIT=+2.030, TO=0.131  -- CLEARS RAISED BAR

R8b validates that AND tests two more mechanically distinct families:

  Family L (liquidity-flow short-attention -- N3 flipped):
    M1_liqflip_w20D10  -- confirm the sign-flip
    M2_liqflip_w60D10  -- 60d lookback as robustness sibling

  Family V (volume-burst time-series reversal):
    M3_volz60_D20      -- ts_zscore(volume, 60) reversed

  Family C (intraday close-strength reversal):
    M4_clstrength_D20  -- (close-low)/(high-low) reversed
    M5_clstrength_D30  -- same with longer decay for lower TO

Common to all: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000,
delay=1, pasteurization=ON. Filter: SH>1.35, FIT>1.0, TO<0.15.

Goal: at least 3 distinct mechanism families surviving.
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
log = logging.getLogger("r8b")

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
        "label": "M1_liqflip_w20D10",
        "family": "L_liquidity_flow",
        "expression": (
            "zscore(reverse(ts_decay_linear(divide(subtract(adv20, "
            "ts_delay(adv20, 20)), ts_delay(adv20, 20)), 10)))"
        ),
        "notes": "20d delta in adv20, REVERSED; rising-liquidity stocks underperform",
    },
    {
        "label": "M2_liqflip_w60D10",
        "family": "L_liquidity_flow",
        "expression": (
            "zscore(reverse(ts_decay_linear(divide(subtract(adv20, "
            "ts_delay(adv20, 60)), ts_delay(adv20, 60)), 10)))"
        ),
        "notes": "60d delta in adv20, REVERSED (longer-lookback robustness sibling)",
    },
    {
        "label": "M3_volz60_D20",
        "family": "V_volume_burst",
        "expression": "zscore(reverse(ts_decay_linear(ts_zscore(volume, 60), 20)))",
        "notes": "60d ts_zscore of raw volume, REVERSED; volume spikes mean-revert",
    },
    {
        "label": "M4_clstrength_D20",
        "family": "C_close_strength",
        "expression": (
            "zscore(reverse(ts_decay_linear(divide(subtract(close, low), "
            "subtract(high, low)), 20)))"
        ),
        "notes": "(close-low)/(high-low) intraday position, REVERSED; strong-close stocks fade",
    },
    {
        "label": "M5_clstrength_D30",
        "family": "C_close_strength",
        "expression": (
            "zscore(reverse(ts_decay_linear(divide(subtract(close, low), "
            "subtract(high, low)), 30)))"
        ),
        "notes": "same close-strength signal with 30d outer decay (lower TO)",
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

    session_id = f"{dt.datetime.now():%Y%m%d}_diversification_r8b_orthogonal_v2_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"Deliver 3 alphas in mechanically-distinct families.\n"
        f"3 families (liquidity-flow, volume-burst, close-strength), 5 variants.\n"
        f"Filter: SH>{SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
    )
    log.info(f"Session: {session_dir}")

    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  [{v['family']}]")
        log.info(f"      {v['notes']}")
        log.info(f"      expr: {v['expression']}")
        res = r5.submit(cm.session, v["expression"], BASE)
        entry = {
            "variant": v["label"],
            "family": v["family"],
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

    md = f"# Round 8b - orthogonal mechanisms v2\n\n"
    md += f"3 families (liquidity-flow / volume-burst / close-strength), 5 variants.\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH > {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"## Results\n\n"
    md += f"| variant | family | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] > SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['family']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['family']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"

    families_covered = sorted({r["family"] for r in survivors})
    md += f"\n**Distinct families covered: {len(families_covered)}** ({', '.join(families_covered) if families_covered else 'none'})\n"

    (session_dir / "outputs" / "orthogonal_v2_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 8b final - orthogonal mechanisms v2\n\n"
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
