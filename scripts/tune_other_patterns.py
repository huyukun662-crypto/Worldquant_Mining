"""Round 54: completely different expression patterns -- no returns*volwt skeleton.

Switching away from any (returns/accel × vol-weight × decay × reverse) family.
5 fresh patterns using different building blocks:

  CCC1 pure intraday geometry (range x close-strength) -- no returns
  CCC2 volume acceleration only -- no returns
  CCC3 close vs vwap deviation
  CCC4 rank(returns) - rank(volume) -- pure cross-sectional, no decay
  CCC5 vol-ratio direct (NO accel multiplication)
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r54")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VARIANTS = [
    {"label": "CCC1_range_x_clstrength",
     "logic": "range*close-strength (pure intraday geometry, no returns)",
     "expression": (
         "zscore(reverse(ts_decay_linear(multiply("
         "divide(subtract(high, low), close), "
         "divide(subtract(close, low), subtract(high, low))), 25)))")},
    {"label": "CCC2_volume_acceleration",
     "logic": "1d change in volume/adv20 (no returns)",
     "expression": (
         "zscore(reverse(ts_decay_linear(subtract("
         "divide(volume, adv20), ts_delay(divide(volume, adv20), 1)), 25)))")},
    {"label": "CCC3_close_vs_vwap",
     "logic": "close vs vwap deviation, reversed",
     "expression": (
         "zscore(reverse(ts_decay_linear("
         "divide(subtract(close, vwap), vwap), 25)))")},
    {"label": "CCC4_rank_returns_minus_rank_vol",
     "logic": "rank(returns) - rank(volume) -- pure XS, no decay",
     "expression": (
         "zscore(subtract(rank(returns), rank(volume)))")},
    {"label": "CCC5_vol_ratio_direct",
     "logic": "ts_std_dev(returns,5)/ts_std_dev(returns,60) -- standalone, no accel",
     "expression": (
         "zscore(reverse(ts_decay_linear("
         "divide(ts_std_dev(returns, 5), ts_std_dev(returns, 60)), 25)))")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r54_other_patterns_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "5 completely different expression patterns (no returns*volwt skeleton).\n"
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
    md = "# R54 other patterns\n\n"
    md += ("| variant | logic | SH | TO | FIT | conc | sub | passes? |\n"
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
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['logic']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['logic']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
