"""Round 59: lift news-smoothed signals over SH>=1.75 with rv-scaling
and/or smaller universe.

R58 showed news_smoothed alphas plateau at SH 1.3-1.5. Pure smoothing
doesn't break the ceiling. Two new levers:

  (1) rv multiplier: multiply by ts_std_dev(returns,20) before decay.
      Adds risk-conditional scaling -- proven to lift PV alphas (R47
      win uses this; SH 2.33). Slow-moving news rank x rv keeps the
      news content but lets vol bursts drive position size.

  (2) Smaller universe: TOP1000 or TOP500. Fewer names, news signal
      has more relative bite. Also fewer concentrations to fix.

5 variants:
  DD1 novelty_20 x rv x rev5 x volwt D=25  (TOP3000)   -- rv boost
  DD2 impact_20  x rv x rev5 x volwt D=25  (TOP3000)   -- rv boost
  DD3 novelty_20 x rev5 x volwt D=25       (TOP1000)   -- universe boost
  DD4 impact_20  x rev5 x volwt D=25       (TOP1000)   -- universe boost
  DD5 (novelty_20 + impact_20) x rv x rev5 x volwt D=25 (TOP3000)
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r59")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(univ: str = "TOP3000", trunc: float = 0.08):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": univ,
        "delay": 1, "decay": 8, "truncation": trunc, "neutralization": "SUBINDUSTRY",
        "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
        "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
        "testPeriod": "P0Y0M",
    }


VOLWT = "log(add(divide(volume, adv20), 1))"
RV = "ts_std_dev(returns, 20)"
REV5 = "reverse(ts_zscore(returns, 5))"
NOVELTY = "rank(ts_mean(mean_event_novelty_score, 20))"
IMPACT = "rank(ts_mean(mean_news_impact_projection, 20))"

VARIANTS = [
    {"label": "DD1_novelty_rv_TOP3000",
     "rationale": "novelty_20 x rv x rev5 x volwt D=25",
     "settings": settings("TOP3000"),
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply(multiply("
         f"{NOVELTY}, {RV}), {REV5}), {VOLWT}), 25))")},
    {"label": "DD2_impact_rv_TOP3000",
     "rationale": "impact_20 x rv x rev5 x volwt D=25",
     "settings": settings("TOP3000"),
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply(multiply("
         f"{IMPACT}, {RV}), {REV5}), {VOLWT}), 25))")},
    {"label": "DD3_novelty_TOP1000",
     "rationale": "novelty_20 x rev5 x volwt D=25 on TOP1000",
     "settings": settings("TOP1000"),
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"{NOVELTY}, {REV5}), {VOLWT}), 25))")},
    {"label": "DD4_impact_TOP1000",
     "rationale": "impact_20 x rev5 x volwt D=25 on TOP1000",
     "settings": settings("TOP1000"),
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply("
         f"{IMPACT}, {REV5}), {VOLWT}), 25))")},
    {"label": "DD5_combo_rv_TOP3000",
     "rationale": "(novelty_20+impact_20) x rv x rev5 x volwt D=25",
     "settings": settings("TOP3000"),
     "expression": (
         f"zscore(ts_decay_linear(multiply(multiply(multiply(add("
         f"{NOVELTY}, {IMPACT}), {RV}), {REV5}), {VOLWT}), 25))")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r59_news_rvboost_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Boost news-smoothed alphas with rv multiplier or smaller universe.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        s = v["settings"]
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}: {v['rationale']}")
        log.info(f"      universe={s['universe']} trunc={s['truncation']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], s)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "rationale": v["rationale"],
                 "universe": s['universe'], "trunc": s['truncation'],
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
    md = "# R59 news rv-boost + smaller universe\n\n"
    md += ("| variant | universe | rationale | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---|---|---:|---:|---:|---|---|---|\n")
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
        md += (f"| {r['variant']} | {r['universe']} | {r['rationale']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r.get('universe','?')} | {r['rationale']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
