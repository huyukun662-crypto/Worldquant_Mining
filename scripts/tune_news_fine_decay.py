"""Round 61: thread the needle -- impact_s20 at SH>=1.5 ^ TO<0.20.

R60 boundary (impact, smooth20, rev5):
  D=30 -> SH=1.53 TO=0.209  (SH ok, TO over by 0.009)
  D=35 -> SH=1.46 TO=0.198  (TO ok, SH under by 0.04)

The crossover is between D=30 and D=35. Fine sweep D=31..34, plus two
shape tweaks that lower TO without the SH hit of pure decay:
  - smooth25 (between s20 best-SH and s30 too-flat)
  - rev6 reversal window (marginally slower kernel)

5 variants, all impact field, conc+sub already PASS in R60:
  FF1 impact s20 rev5 D=31
  FF2 impact s20 rev5 D=32
  FF3 impact s20 rev5 D=33
  FF4 impact s25 rev5 D=30
  FF5 impact s20 rev6 D=30
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r61")
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
IMP = "mean_news_impact_projection"


def expr(smooth: int, rev_w: int, d: int) -> str:
    return (
        f"zscore(ts_decay_linear(multiply(multiply("
        f"rank(ts_mean({IMP}, {smooth})), "
        f"reverse(ts_zscore(returns, {rev_w}))), {VOLWT}), {d}))"
    )


VARIANTS = [
    {"label": "FF1_s20_rev5_D31", "expression": expr(20, 5, 31)},
    {"label": "FF2_s20_rev5_D32", "expression": expr(20, 5, 32)},
    {"label": "FF3_s20_rev5_D33", "expression": expr(20, 5, 33)},
    {"label": "FF4_s25_rev5_D30", "expression": expr(25, 5, 30)},
    {"label": "FF5_s20_rev6_D30", "expression": expr(20, 6, 30)},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r61_news_fine_decay_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Fine decay sweep to land impact alpha at SH>=1.5 ^ TO<0.20.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"], **res}
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
    md = "# R61 news fine decay sweep (target SH>=1.5 ^ TO<0.20)\n\n"
    md += ("| variant | SH | TO | FIT | conc | sub | passes(1.5)? |\n"
           "|---|---:|---:|---:|---|---|---|\n")
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
        md += (f"| {r['variant']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors (SH>=1.5 ^ TO<0.20): {len(survivors)}/{len(results)}**\n"
    if survivors:
        md += "\n## Survivor expressions\n\n"
        for r in survivors:
            md += (f"### {r['variant']} -- alpha {r.get('alpha_id','?')}\n"
                   f"SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} FIT={r['fitness']:+.3f}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
