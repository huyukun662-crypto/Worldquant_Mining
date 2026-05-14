"""Round 58: push news-smoothed alphas across SH>=1.75 ^ TO<0.20.

R57b near-misses (all WQ checks PASS):
  BB3 novelty smoothed(20) D=25  SH=1.50 TO=0.225 FIT=0.89
  BB4 impact  smoothed(20) D=25  SH=1.57 TO=0.223 FIT=1.06

Need: TO 0.22 -> <0.20  AND  SH 1.5 -> >=1.75  AND  FIT -> >1.25

Levers:
  (a) heavier smoothing (40d/60d) lowers TO further
  (b) longer decay (35-40) lifts SH on slow signals
  (c) larger reversal window (10d not 5d) reduces noise
  (d) news_novelty x news_impact (signal blend)
  (e) lower universe (TOP1000) where news has more bite

5 variants:
  CC1 novelty smoothed(40)  rev5 vol D=25
  CC2 impact  smoothed(40)  rev5 vol D=25
  CC3 novelty smoothed(60)  rev10 vol D=35
  CC4 impact  smoothed(60)  rev10 vol D=35
  CC5 (novelty + impact) smoothed(20) rev5 vol D=25  (signal stack)
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r58")
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

VARIANTS = [
    {"label": "CC1_novelty_40_D25",
     "rationale": "novelty smoothed(40), rev5, D=25",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"rank(ts_mean(mean_event_novelty_score, 40)), "
         f"reverse(ts_zscore(returns, 5))), {VOLWT}), 25))")},
    {"label": "CC2_impact_40_D25",
     "rationale": "impact smoothed(40), rev5, D=25",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"rank(ts_mean(mean_news_impact_projection, 40)), "
         f"reverse(ts_zscore(returns, 5))), {VOLWT}), 25))")},
    {"label": "CC3_novelty_60_rev10_D35",
     "rationale": "novelty smoothed(60), rev10, D=35",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"rank(ts_mean(mean_event_novelty_score, 60)), "
         f"reverse(ts_zscore(returns, 10))), {VOLWT}), 35))")},
    {"label": "CC4_impact_60_rev10_D35",
     "rationale": "impact smoothed(60), rev10, D=35",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"rank(ts_mean(mean_news_impact_projection, 60)), "
         f"reverse(ts_zscore(returns, 10))), {VOLWT}), 35))")},
    {"label": "CC5_novelty_plus_impact_20",
     "rationale": "rank(novelty_20)+rank(impact_20), rev5, D=25",
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply(add("
         f"rank(ts_mean(mean_event_novelty_score, 20)), "
         f"rank(ts_mean(mean_news_impact_projection, 20))), "
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r58_news_heavier_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Push BB3/BB4 news-smoothed alphas across SH>=1.75 ^ TO<0.20.\n"
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
    md = "# R58 news-heavier-smoothing\n\n"
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
