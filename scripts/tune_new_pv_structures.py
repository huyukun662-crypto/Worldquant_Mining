"""Round 39: NEW PV alphas at SH>=1.75, structurally distinct from
prior R5-R29 families.

Existing PV families to AVOID:
  - Reversal:        zscore(reverse(decay(mult(ts_zscore(returns,W), volwt), D)))
  - Liqflow:         zscore(reverse(decay(div(sub(adv20,prev_adv20), prev_adv20), D)))
  - Intraday-volwt:  zscore(reverse(decay(mult((close-open)/open, volwt), D)))
  - Price-accel:     zscore(reverse(decay(mult(sub(returns, ts_delay(returns,W)), volwt), D)))

5 new structures using high/low/volume in untested combos:

  NN1  daily range / close, vol-weighted, reversed (range mean-reversion)
  NN2  3rd-derivative (jerk) of price, vol-weighted, reversed
  NN3  range-position acceleration, vol-weighted, reversed
  NN4  volume-of-volume (std-dev of relative vol), reversed, smoothed
  NN5  returns x range x vol-weight, reversed (compound triple)

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.
Filter: SH>=1.75, FIT>1.25, TO<0.20.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r39")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.08, "neutralization": "INDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VOLWT = "log(add(divide(volume, adv20), 1))"
ACCEL1 = "subtract(returns, ts_delay(returns, 1))"
RANGE = "divide(subtract(high, low), close)"
RANGE_POS = "divide(subtract(close, low), subtract(high, low))"

VARIANTS = [
    {
        "label": "NN1_range_volwt_rev",
        "logic": "daily range / close, vol-weighted, REVERSED (range mean-reversion)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply({RANGE}, {VOLWT}), 20)))"
        ),
    },
    {
        "label": "NN2_jerk_volwt_rev",
        "logic": "3rd derivative (jerk) of price, vol-weighted, REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"subtract({ACCEL1}, ts_delay({ACCEL1}, 1)), {VOLWT}), 30)))"
        ),
    },
    {
        "label": "NN3_rangepos_accel_volwt_rev",
        "logic": "range-position acceleration, vol-weighted, REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply("
            f"subtract({RANGE_POS}, ts_delay({RANGE_POS}, 1)), {VOLWT}), 30)))"
        ),
    },
    {
        "label": "NN4_volofvol_rev",
        "logic": "volume-of-volume (std-dev of relative volume), REVERSED",
        "expression": (
            f"zscore(reverse(ts_decay_linear("
            f"ts_std_dev(divide(volume, adv20), 20), 30)))"
        ),
    },
    {
        "label": "NN5_ret_range_volwt_rev",
        "logic": "returns x range x vol-weight, REVERSED (compound triple)",
        "expression": (
            f"zscore(reverse(ts_decay_linear(multiply(multiply(returns, "
            f"{RANGE}), {VOLWT}), 20)))"
        ),
    },
]


def _load(p, name):
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

    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r39_new_pv_structures_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "5 NEW PV alphas at SH>=1.75 -- structures untested in prior R5-R29.\n"
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
        entry = {"variant": v["label"], "logic": v["logic"],
                 "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} RET={res['returns']:+.3f} "
                     f"checks={res['checks_passed']}/{res['checks_total']}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")
    md = "# R39 NEW PV alphas (target SH>=1.75 TO<0.2 FIT>1.25)\n\n"
    md += "| variant | logic | SH | TO | FIT | survives? |\n|---|---|---:|---:|---:|---|\n"
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        passes = r['sharpe'] >= 1.75 and r['turnover'] < 0.20 and r['fitness'] > 1.25
        tag = "**YES**" if passes else "no"
        md += (f"| {r['variant']} | {r['logic']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | FAIL | - | - | no |\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
