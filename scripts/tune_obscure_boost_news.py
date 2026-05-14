"""R57b: complete BB3-BB5 news-smoothing variants (R57 timed out mid-run).

R57 BB1 (buyback x R47 kernel) SH=0.98 -- R47 kernel muddied buyback rank
R57 BB2 (shares_count x R47 kernel) SH=1.05 -- same finding

So the R47 multiplier degrades, NOT amplifies, slow-moving fundamental ranks.
Keep going on news-smoothing path (BB3/BB4/BB5) -- these were the other path.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r57b")
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
BUYBACK = "subtract(ts_delay(common_shares_outstanding_total, 60), common_shares_outstanding_total)"

VARIANTS = [
    {"label": "BB3_news_novelty_smoothed",
     "rationale": "rank(ts_mean(novelty,20)) * rev * volwt, D=25",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"rank(ts_mean(mean_event_novelty_score, 20)), "
         f"reverse(ts_zscore(returns, 5))), {VOLWT}), 25))")},
    {"label": "BB4_news_impact_smoothed",
     "rationale": "rank(ts_mean(impact,20)) * rev * volwt, D=25",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"rank(ts_mean(mean_news_impact_projection, 20)), "
         f"reverse(ts_zscore(returns, 5))), {VOLWT}), 25))")},
    {"label": "BB5_buyback_x_novelty_smoothed",
     "rationale": "rank(buyback) * rank(ts_mean(novelty,20)) * rev * volwt, D=25",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply(multiply("
         f"rank({BUYBACK}), rank(ts_mean(mean_event_novelty_score, 20))), "
         f"reverse(ts_zscore(returns, 5))), {VOLWT}), 25))")},
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    r5 = _load(REPO / "scripts" / "run_5agent_workflow.py", "r5")
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r57b_news_smoothing_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Finish R57: news-smoothed obscure-field variants.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: {v['rationale']}")
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
                if chk.get("name") in ("CONCENTRATED_WEIGHT","LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R57b news-smoothed alphas\n\n"
    md += ("| variant | rationale | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---|---:|---:|---:|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        conc_ok = conc.get('result')=='PASS'
        sub_ok = sub.get('result')=='PASS'
        all_pass = (r['sharpe']>=1.75 and r['turnover']<0.20
                    and r['fitness']>1.25 and conc_ok and sub_ok)
        if all_pass: survivors.append(r)
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
