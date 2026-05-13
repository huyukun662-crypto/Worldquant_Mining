"""Round 48: 5 NEW logic families at SH>=1.75 TO<0.2 FIT>1.25 + ALL WQ CHECKS PASS.

Existing PV families to AVOID:
  - close-close reversal (R5-7): ts_zscore(returns,W) * volwt
  - liquidity-flow (R8b/c):       adv20 delta
  - intraday (R8e):                (close-open)/open * volwt
  - price-accel (R12/15/16/28/29): subtract(returns, ts_delay(returns,W)) * volwt
  - rv-accel (R45-47):            ts_std_dev(returns,X) * accel * volwt

5 NEW logical families (distinct multiplicative interactions):

  WW1  rv x reversal x volwt reverse
       ts_std_dev(returns,20) * ts_zscore(returns,5) -- vol-amplified reversal
  WW2  rv x intraday x volwt reverse
       ts_std_dev(returns,20) * (close-open)/open -- vol-amplified intraday
  WW3  range x accel x volwt reverse
       (high-low)/close * accel -- range-amplified accel (different multiplier)
  WW4  abs(returns) x reversal x volwt reverse
       abs(returns) * ts_zscore(returns,5) -- magnitude-weighted reversal
  WW5  rv x range x volwt reverse
       ts_std_dev(returns,20) * (high-low)/close -- vol x range (no return-direction)

Settings: zscore, SUBINDUSTRY (proven best), decay=8, trunc=0.05,
TOP3000, delay=1, pasteurization=ON, nanHandling=OFF.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r48")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VOLWT = "log(add(divide(volume, adv20), 1))"
RV = "ts_std_dev(returns, 20)"
REVERSAL = "ts_zscore(returns, 5)"
INTRADAY = "divide(subtract(close, open), open)"
ACCEL = "subtract(returns, ts_delay(returns, 2))"
RANGE = "divide(subtract(high, low), close)"

VARIANTS = [
    {"label": "WW1_rv_reversal_volwt",
     "logic": "rv x reversal x volwt rev (vol-amplified reversal)",
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply("
                    f"{RV}, {REVERSAL}), {VOLWT}), 25)))")},
    {"label": "WW2_rv_intraday_volwt",
     "logic": "rv x intraday x volwt rev",
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply("
                    f"{RV}, {INTRADAY}), {VOLWT}), 25)))")},
    {"label": "WW3_range_accel_volwt",
     "logic": "range x accel x volwt rev (range-amplified accel)",
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply("
                    f"{RANGE}, {ACCEL}), {VOLWT}), 25)))")},
    {"label": "WW4_absret_reversal_volwt",
     "logic": "abs(returns) x reversal x volwt rev",
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply("
                    f"abs(returns), {REVERSAL}), {VOLWT}), 25)))")},
    {"label": "WW5_rv_range_volwt",
     "logic": "rv x range x volwt rev (no return direction)",
     "expression": (f"zscore(reverse(ts_decay_linear(multiply(multiply("
                    f"{RV}, {RANGE}), {VOLWT}), 25)))")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r48_new_logic_families_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "5 NEW logic families at SH>=1.75 + ALL WQ CHECKS PASS.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/5] {v['label']}: {v['logic']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "logic": v["logic"],
                 "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R48 NEW logic families\n\n"
    md += ("| variant | logic | SH | TO | FIT | conc | sub-uni | passes? |\n"
           "|---|---|---:|---:|---:|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        conc_pass = conc.get('result') == 'PASS'
        sub_pass = sub.get('result') == 'PASS'
        all_pass = (r['sharpe'] >= 1.75 and r['turnover'] < 0.20
                    and r['fitness'] > 1.25 and conc_pass and sub_pass)
        if all_pass:
            survivors.append(r)
        conc_cell = "PASS" if conc_pass else f"FAIL({conc.get('value','?')})"
        sub_cell = "PASS" if sub_pass else f"FAIL({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['logic']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {conc_cell} | "
                f"{sub_cell} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Fully-passing survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
