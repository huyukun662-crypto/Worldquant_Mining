"""Round 62: break the news_impact TO floor via truncation + trade_when.

R61 best (FF5): impact s20 rev6 D30 -> SH=1.59 TO=0.209 FIT=1.14, all
WQ checks PASS. Pure decay can't get TO<0.20 without dropping SH<1.5.

Two levers that cut TO without flattening the signal:
  1. truncation: caps per-name weight -> fewer big rebalances. Sweep
     0.10 / 0.12 / 0.15 (base was 0.08).
  2. trade_when: hold prior position on quiet days instead of
     rebalancing. Two gates:
       - liquidity gate: only rebalance when volume > adv20
       - news-freshness gate: only rebalance when |z(impact,20)| > 0.5

5 variants, all on the FF5 base expression:
  GG1 FF5  truncation=0.10
  GG2 FF5  truncation=0.12
  GG3 FF5  truncation=0.15
  GG4 FF5 + trade_when(volume>adv20)         truncation=0.08
  GG5 FF5 + trade_when(|z(impact,20)|>0.5)   truncation=0.08

Target: SH>=1.5, TO<0.20, FIT>1.0, conc+sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r62")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def base_settings(truncation: float) -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": truncation,
        "neutralization": "SUBINDUSTRY", "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


VOLWT = "log(add(divide(volume, adv20), 1))"
IMP = "mean_news_impact_projection"
# FF5 base: impact s20, rev6, decay-linear D30, zscore-wrapped
FF5 = (
    f"zscore(ts_decay_linear(multiply(multiply("
    f"rank(ts_mean({IMP}, 20)), reverse(ts_zscore(returns, 6))), {VOLWT}), 30))"
)
GG4 = f"trade_when(greater(volume, adv20), {FF5}, -1)"
GG5 = f"trade_when(greater(abs(ts_zscore({IMP}, 20)), 0.5), {FF5}, -1)"

VARIANTS = [
    {"label": "GG1_FF5_trunc0.10", "expression": FF5, "truncation": 0.10},
    {"label": "GG2_FF5_trunc0.12", "expression": FF5, "truncation": 0.12},
    {"label": "GG3_FF5_trunc0.15", "expression": FF5, "truncation": 0.15},
    {"label": "GG4_FF5_tw_liquidity", "expression": GG4, "truncation": 0.08},
    {"label": "GG5_FF5_tw_newsfresh", "expression": GG5, "truncation": 0.08},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r62_news_trunc_tradewhen_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Break news_impact TO floor (~0.20) via truncation sweep + trade_when gating.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}  (trunc={v['truncation']})")
        log.info(f"      expr: {v['expression']}")
        settings = base_settings(v["truncation"])
        try:
            res = r5.submit(cm.session, v["expression"], settings)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"],
                 "truncation": v["truncation"], **res}
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
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")
    md = "# R62 news truncation + trade_when (target SH>=1.5 ^ TO<0.20)\n\n"
    md += ("| variant | trunc | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---:|---:|---:|---:|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        conc_ok = conc.get('result')=='PASS'
        sub_ok = sub.get('result')=='PASS'
        all_pass = (r['sharpe']>=1.5 and r['turnover']<0.20 and conc_ok and sub_ok)
        if all_pass: survivors.append(r)
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['truncation']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | {r['truncation']} | FAIL | - | - | - | - | no |  "
               f"{r.get('error','?')[:80]}\n")
    md += f"\n**Survivors (SH>=1.5 ^ TO<0.20): {len(survivors)}/{len(results)}**\n"
    if survivors:
        md += "\n## Survivor expressions\n\n"
        for r in survivors:
            md += (f"### {r['variant']} -- alpha {r.get('alpha_id','?')}\n"
                   f"SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
                   f"FIT={r['fitness']:+.3f} trunc={r['truncation']}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
