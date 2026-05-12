"""Round 20: fix weight-concentration on R3/R4/Q1 IV skew alphas.

User reported WQ Brain check failures:
  - "Weight concentration 50.00% above 10% cutoff" (CONCENTRATED_WEIGHT)
  - "Sub-universe Sharpe 0.86 below 0.97 cutoff" (LOW_SUB_UNIVERSE_SHARPE)

Root cause: option IV data is sparse across TOP3000 -- on some days,
only a few stocks have valid IV values, so zscore() puts disproportionate
weight on those few names.

Fix strategies (grid):

  S1 R3 with quantile(driver="uniform") -- spreads weights uniformly
  S2 R3 with SUBINDUSTRY neutralization (finer residualization)
  S3 R3 with quantile + SUBINDUSTRY (combined fix)
  S4 R4 (vol-weighted) with quantile + SUBINDUSTRY
  S5 Q1 (30-tenor canonical) with quantile + SUBINDUSTRY

If quantile fixes the concentration but maintains SH, the user has
clean deliverables. `quantile` flattens the weight distribution while
preserving the rank ordering of the signal.

TOP3000, delay=1, decay=8, truncation=0.08 (will reduce later if needed),
pasteurization=ON, nanHandling=ON.
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
log = logging.getLogger("r20")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 8,
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

SKEW_180 = "subtract(implied_volatility_put_180, implied_volatility_call_180)"
SKEW_30 = "subtract(implied_volatility_put_30, implied_volatility_call_30)"

# Original R3 form (with zscore -- has concentration issue):
#   zscore(reverse(ts_decay_linear(SKEW_180, 20)))
# Original R4 form:
#   zscore(reverse(ts_decay_linear(multiply(SKEW_30, historical_volatility_20), 20)))
# Original Q1 form:
#   zscore(reverse(ts_decay_linear(SKEW_30, 20)))


VARIANTS = [
    {
        "label": "S1_R3_quantile",
        "fix": "quantile(uniform) replaces zscore",
        "neut": "INDUSTRY",
        "expression": (
            f'quantile(reverse(ts_decay_linear({SKEW_180}, 20)), driver="uniform")'
        ),
    },
    {
        "label": "S2_R3_SUBINDUSTRY",
        "fix": "SUBINDUSTRY neut (finer residualization)",
        "neut": "SUBINDUSTRY",
        "expression": (
            f"zscore(reverse(ts_decay_linear({SKEW_180}, 20)))"
        ),
    },
    {
        "label": "S3_R3_quantile_SUBIN",
        "fix": "quantile + SUBINDUSTRY (combined)",
        "neut": "SUBINDUSTRY",
        "expression": (
            f'quantile(reverse(ts_decay_linear({SKEW_180}, 20)), driver="uniform")'
        ),
    },
    {
        "label": "S4_R4_quantile_SUBIN",
        "fix": "R4 vol-wt + quantile + SUBINDUSTRY",
        "neut": "SUBINDUSTRY",
        "expression": (
            f'quantile(reverse(ts_decay_linear('
            f'multiply({SKEW_30}, historical_volatility_20), 20)), driver="uniform")'
        ),
    },
    {
        "label": "S5_Q1_quantile_SUBIN",
        "fix": "Q1 30-tenor + quantile + SUBINDUSTRY",
        "neut": "SUBINDUSTRY",
        "expression": (
            f'quantile(reverse(ts_decay_linear({SKEW_30}, 20)), driver="uniform")'
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r20_iv_skew_fixes_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Fix CONCENTRATED_WEIGHT + LOW_SUB_UNIVERSE_SHARPE on IV skew alphas.\n"
        "Strategy: quantile() wrapper + SUBINDUSTRY neut.\n"
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
            # Extract concentration / sub_universe_sharpe check details
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} "
                             f"limit={chk.get('limit')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")

    md = f"# Round 20 - fix CONCENTRATED_WEIGHT + LOW_SUB_UNIVERSE_SHARPE on IV skew\n\n"
    md += f"## Results (ranked by SH)\n\n"
    md += f"| variant | fix | neut | SH | TO | FIT | RET | DD | checks |\n"
    md += f"|---|---|---|---:|---:|---:|---:|---:|---|\n"
    ok_results = [r for r in results if r.get("ok")]
    ok_results.sort(key=lambda r: r["sharpe"], reverse=True)
    for r in ok_results:
        md += (f"| {r['variant']} | {r['fix']} | {r['neut']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{r['returns']:+.3f} | {r['drawdown']:.3f} | "
                f"{r['checks_passed']}/{r['checks_total']} |\n")
    for r in [r for r in results if not r.get("ok")]:
        md += (f"| {r['variant']} | {r['fix']} | {r['neut']} | FAIL | - | - | - | - | - |\n")
    (session_dir / "outputs" / "iv_skew_fixes_sweep.md").write_text(md)
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(
        json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
