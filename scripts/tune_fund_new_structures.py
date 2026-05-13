"""Round 49: Fundamental alphas with TRULY DIFFERENT structures.

Previous skeleton (R5-R48): zscore(reverse(ts_decay_linear(multiply(...), D)))
User says structure is too repetitive. R49 tries 5 truly different
structural forms using fundamental fields:

  XX1  E/P x reversal smoothed -- E/P-weighted price reversal
       (still uses decay+reverse but fundamental as the multiplier)
  XX2  ROE x accel smoothed -- ROE-weighted price accel
       (same skeleton but fundamental gate)
  XX3  E/P 1-year change -- subtract(E/P[t], E/P[t-252])
       (NO decay, NO reverse -- raw change signal)
  XX4  trade_when conditional reversal -- only trade when cashflow positive
       (trade_when STRUCTURE -- never used before)
  XX5  rank-of-ranks compound -- divide(rank(E/P), rank(asset_growth))
       (NO time-series smoothing -- pure cross-sectional)

Filter: SH>=1.75, TO<0.20, FIT>1.25, all WQ checks PASS.
Realistic expectation: fundamentals cap at SH=0.7 per R17-R38. The
PV-blend (XX1/XX2) may hit higher; pure fundamental (XX3/XX5) likely
under 1.0; trade_when (XX4) unknown.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r49")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VARIANTS = [
    {"label": "XX1_EP_reversal",
     "logic": "E/P x reversal smoothed (fundamental-weighted PV reversal)",
     "expression": (
         "zscore(reverse(ts_decay_linear(multiply("
         "divide(eps, close), ts_zscore(returns, 5)), 20)))")},
    {"label": "XX2_ROE_accel",
     "logic": "ROE x accel smoothed (quality-weighted PV accel)",
     "expression": (
         "zscore(reverse(ts_decay_linear(multiply("
         "return_equity, subtract(returns, ts_delay(returns, 2))), 25)))")},
    {"label": "XX3_EP_yoy_change",
     "logic": "1-year change in E/P (NO decay, NO reverse)",
     "expression": (
         "zscore(subtract(divide(eps, close), "
         "ts_delay(divide(eps, close), 252)))")},
    {"label": "XX4_trade_when_cf",
     "logic": "trade_when cashflow_op>0: do reversal (TRADE_WHEN structure)",
     "expression": (
         "trade_when(greater(cashflow_op, 0), "
         "zscore(reverse(ts_zscore(returns, 5))), 0)")},
    {"label": "XX5_rank_of_ranks",
     "logic": "divide(rank(E/P), rank(asset_growth)) -- cross-sectional only",
     "expression": (
         "zscore(divide(rank(divide(eps, close)), "
         "rank(divide(subtract(assets, ts_delay(assets, 252)), "
         "ts_delay(assets, 252)))))")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r49_fund_new_structures_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Fundamental alphas with TRULY different structures.\n"
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
    md = "# R49 fundamental new structures\n\n"
    md += ("| variant | logic | SH | TO | FIT | conc | sub-uni | passes? |\n"
           "|---|---|---:|---:|---:|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')], key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        conc_ok = conc.get('result') == 'PASS'
        sub_ok = sub.get('result') == 'PASS'
        all_pass = (r['sharpe'] >= 1.75 and r['turnover'] < 0.20
                    and r['fitness'] > 1.25 and conc_ok and sub_ok)
        if all_pass:
            survivors.append(r)
        conc_cell = "PASS" if conc_ok else f"FAIL({conc.get('value','?')})"
        sub_cell = "PASS" if sub_ok else f"FAIL({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['logic']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {conc_cell} | "
                f"{sub_cell} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
