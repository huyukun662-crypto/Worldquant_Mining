"""Round 57: boost R56 obscure-field signals to clear SH>=1.75.

R56 findings:
  OBS2 buyback (rank(d_shares_60) x rev x volwt) ........... SH=1.22 TO=0.22  P/P
  OBS3 news_novelty ........................................ SH=1.36 TO=1.07  P/F
  OBS4 news_impact ......................................... SH=1.27 TO=0.66  P/F
  OBS1 sbp_decline ......................................... SH=0.83 TO=0.22  P/P
  OBS5 social_vol .......................................... SH=0.32 TO=0.20  P/P

Two recovery strategies:
  (A) rare-field x R47 rv*accel*volwt kernel  -- lifts SH dramatically
  (B) ts_mean(20) smoothing on news           -- kills TO blowout

5 variants:
  BB1  buyback x R47 kernel
  BB2  shares_out_count x R47 kernel
  BB3  news_novelty SMOOTHED ts_mean(20) x rev x volwt
  BB4  news_impact SMOOTHED ts_mean(20) x rev x volwt
  BB5  buyback x R47 kernel * news_novelty smoothed (4-way blend)

Settings: USA TOP3000 delay=1 trunc=0.08 SUBINDUSTRY (carry from R56).
Filter: SH>=1.75 ^ TO<0.20 ^ FIT>1.25 ^ CONC/SUB PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r57")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.08, "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

VOLWT = "log(add(divide(volume, adv20), 1))"
RV = "ts_std_dev(returns, 20)"
ACCEL = "subtract(returns, ts_delay(returns, 2))"
# Buyback signal: positive when shares shrink (delay - now > 0)
BUYBACK = "subtract(ts_delay(common_shares_outstanding_total, 60), common_shares_outstanding_total)"
SHARES_COUNT = "subtract(ts_delay(common_stock_shares_outstanding_count, 60), common_stock_shares_outstanding_count)"


VARIANTS = [
    # buyback tilts the R47 winning kernel
    {"label": "BB1_buyback_x_R47kernel",
     "rationale": "rank(buyback) * R47(rv*accel*volwt)",
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply(rank({BUYBACK}), "
         f"multiply(multiply({RV}, {ACCEL}), {VOLWT})), 25)))")},
    # shares-count sibling (different field, same idea)
    {"label": "BB2_sharescount_x_R47kernel",
     "rationale": "rank(shares_count_delta) * R47(rv*accel*volwt)",
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply(rank({SHARES_COUNT}), "
         f"multiply(multiply({RV}, {ACCEL}), {VOLWT})), 25)))")},
    # news_novelty smoothed 20d -> tame TO
    {"label": "BB3_news_novelty_smoothed",
     "rationale": "rank(ts_mean(novelty,20)) * rev * volwt, D=25",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"rank(ts_mean(mean_event_novelty_score, 20)), "
         f"reverse(ts_zscore(returns, 5))), {VOLWT}), 25))")},
    # news_impact smoothed 20d -> tame TO
    {"label": "BB4_news_impact_smoothed",
     "rationale": "rank(ts_mean(impact,20)) * rev * volwt, D=25",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"rank(ts_mean(mean_news_impact_projection, 20)), "
         f"reverse(ts_zscore(returns, 5))), {VOLWT}), 25))")},
    # 4-way blend: buyback (fundamental) * news_novelty (news) * R47 kernel
    {"label": "BB5_buyback_x_novelty_x_R47",
     "rationale": "rank(buyback) * rank(ts_mean(novelty,20)) * R47 kernel",
     "expression": (
         f"zscore(reverse(ts_decay_linear(multiply(multiply("
         f"rank({BUYBACK}), rank(ts_mean(mean_event_novelty_score, 20))), "
         f"multiply(multiply({RV}, {ACCEL}), {VOLWT})), 25)))")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r57_obscure_boost_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Boost obscure-field signals from R56 to clear SH>=1.75 / TO<0.20.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/5] {v['label']}: {v['rationale']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "rationale": v["rationale"],
                 "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT",
                                        "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} "
                             f"value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R57 obscure-field boost (R47 kernel + smoothing)\n\n"
    md += ("| variant | rationale | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---|---:|---:|---:|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
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
        md += (f"| {r['variant']} | {r['rationale']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['rationale']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
