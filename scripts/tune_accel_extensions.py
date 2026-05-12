"""Round 15: NEW SH>=2 alphas, all-new alpha_ids (not reusing R12 W1/W2).

R12 confirmed price-acceleration is the only family delivering SH>=2
on USA TOP3000 INDUSTRY-neutralized. The two existing deliverables:
  W1 (gJmA8a7m, D=30): SH=2.05 TO=0.171
  W2 (YPNr7w6J, D=50): SH=2.03 TO=0.123

R15 mines 5 truly-new alphas in this family by varying the inner
acceleration time-window AND the vol-weight functional form. All
will produce distinct alpha_ids; some are time-scale siblings of
W1/W2 (different acc window) while others change the weight form.

5 variants (all decay D=40 -- between W1=30 and W2=50):

  G1  accel(W=2)   * log(vol/adv20+1)   -- 2-day acceleration
  G2  accel(W=3)   * log(vol/adv20+1)   -- 3-day acceleration
  G3  accel(W=5)   * log(vol/adv20+1)   -- 5-day relative move
  G4  accel(W=1)   * (high-low)/close   -- range-weighted (compound)
  G5  accel(W=1)   * ts_zscore(volume, 60) -- alt vol weight

Same proven settings (zscore wrapper, INDUSTRY, decay=8, trunc=0.08,
TOP3000, delay=1, pasteurization=ON, nanHandling=OFF).

Filter: SH>=2.0, FIT>1.0, TO<0.25.
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
log = logging.getLogger("r15")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

SHARPE_FLOOR = 2.0
FITNESS_FLOOR = 1.0
TURNOVER_CEILING = 0.25

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


def accel(w: int) -> str:
    return f"subtract(returns, ts_delay(returns, {w}))"


VARIANTS = [
    {
        "label": "G1_accel2_volwt_D40",
        "logic": "2-day acceleration, vol-weighted, D=40",
        "weight_kind": "log(vol/adv20+1)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(2)}, {VOLWEIGHT}), 40)))"
        ),
    },
    {
        "label": "G2_accel3_volwt_D40",
        "logic": "3-day acceleration, vol-weighted, D=40",
        "weight_kind": "log(vol/adv20+1)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(3)}, {VOLWEIGHT}), 40)))"
        ),
    },
    {
        "label": "G3_accel5_volwt_D40",
        "logic": "5-day relative move, vol-weighted, D=40",
        "weight_kind": "log(vol/adv20+1)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(5)}, {VOLWEIGHT}), 40)))"
        ),
    },
    {
        "label": "G4_accel1_range_D40",
        "logic": "1-day accel x intraday range (compound), D=40",
        "weight_kind": "(high-low)/close",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(1)}, "
            f"divide(subtract(high, low), close)), 40)))"
        ),
    },
    {
        "label": "G5_accel1_volz_D40",
        "logic": "1-day accel x ts_zscore(volume, 60) (alt vol weight), D=40",
        "weight_kind": "ts_zscore(volume, 60)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({accel(1)}, "
            f"ts_zscore(volume, 60)), 40)))"
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r15_accel_extensions_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        f"5 NEW alpha_ids in price-acc family (different inner accel windows + alt weights).\n"
        f"Filter: SH>={SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, TO<{TURNOVER_CEILING}.\n"
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
            "weight_kind": v["weight_kind"],
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

    md = f"# Round 15 - NEW alpha_ids passing SH>=2.0, TO<0.25\n\n"
    md += f"Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.\n\n"
    md += f"Filter: SH >= {SHARPE_FLOOR} AND FIT > {FITNESS_FLOOR} AND TO < {TURNOVER_CEILING}\n\n"
    md += f"Reference: R12/W1 (gJmA8a7m): SH=+2.050 TO=0.171; R12/W2 (YPNr7w6J): SH=+2.030 TO=0.123\n\n"
    md += f"## Results\n\n"
    md += f"| variant | logic | weight | SH | TO | FIT | RET | DD | checks | survives? |\n"
    md += f"|---|---|---|---:|---:|---:|---:|---:|---|---|\n"
    survivors = []
    for r in results:
        if r.get("ok"):
            passes = (r["sharpe"] >= SHARPE_FLOOR and r["fitness"] > FITNESS_FLOOR
                      and r["turnover"] < TURNOVER_CEILING)
            tag = "**YES**" if passes else "no"
            if passes:
                survivors.append(r)
            md += (f"| {r['variant']} | {r['logic']} | {r['weight_kind']} | "
                    f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                    f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                    f"{r['checks_passed']}/{r['checks_total']} | {tag} |\n")
        else:
            md += (f"| {r['variant']} | {r['logic']} | {r['weight_kind']} | "
                    f"FAIL | - | - | - | - | - | no |\n")
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "accel_extensions_sweep.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))

    summary = (f"# Round 15 final - NEW alpha_ids SH>=2 TO<0.25\n\n"
                f"Variants: {len(results)}\n"
                f"Filter: SH>={SHARPE_FLOOR}, FIT>{FITNESS_FLOOR}, "
                f"TO<{TURNOVER_CEILING}\n"
                f"Survivors: {len(survivors)}/{len(results)}\n")
    if survivors:
        survivors.sort(key=lambda r: r["sharpe"], reverse=True)
        summary += "\n## Survivors (ranked by SH)\n\n"
        for r in survivors:
            summary += (f"### {r['variant']}\n"
                         f"- alpha_id: `{r['alpha_id']}`\n"
                         f"- logic: {r['logic']}\n"
                         f"- weight: {r['weight_kind']}\n"
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
