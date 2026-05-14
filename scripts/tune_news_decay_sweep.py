"""Round 60: lock in obscure-field diversifiers at SH>=1.5 ^ TO<0.20.

User lowered SH bar to 1.5 for low-correlation diversifiers.

R57b BB4 (impact smooth20 rev5 D25): SH=1.57 TO=0.223 -- SH ok, TO over.
R58   CC4 (impact smooth60 rev10 D35): TO=0.196 -- TO ok, but rev10 broke
      LOW_SUB_UNIVERSE_SHARPE and SH fell to 1.13.

Diagnosis: decay D drives TO down; rev10 (not D) is what broke sub-uni.
So: keep rev5, keep smooth20 (best SH), only raise D to pull TO < 0.20.

5 variants sweeping D with rev5 + smooth20 fixed:
  EE1 impact  smooth20 rev5 D=30
  EE2 impact  smooth20 rev5 D=35
  EE3 novelty smooth20 rev5 D=30
  EE4 novelty smooth20 rev5 D=35
  EE5 impact  smooth30 rev5 D=35   (slight extra smoothing)

Target: SH>=1.5, TO<0.20, FIT as high as possible, conc+sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r60")
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
REV5 = "reverse(ts_zscore(returns, 5))"


def expr(field: str, smooth: int, d: int) -> str:
    return (
        f"zscore(ts_decay_linear(multiply(multiply("
        f"rank(ts_mean({field}, {smooth})), {REV5}), {VOLWT}), {d}))"
    )


NOV = "mean_event_novelty_score"
IMP = "mean_news_impact_projection"

VARIANTS = [
    {"label": "EE1_impact_s20_D30",  "expression": expr(IMP, 20, 30)},
    {"label": "EE2_impact_s20_D35",  "expression": expr(IMP, 20, 35)},
    {"label": "EE3_novelty_s20_D30", "expression": expr(NOV, 20, 30)},
    {"label": "EE4_novelty_s20_D35", "expression": expr(NOV, 20, 35)},
    {"label": "EE5_impact_s30_D35",  "expression": expr(IMP, 30, 35)},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r60_news_decay_sweep_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Decay sweep to land obscure-field news alphas at SH>=1.5 ^ TO<0.20.\n"
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
    md = "# R60 news decay sweep (target SH>=1.5 ^ TO<0.20)\n\n"
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
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
