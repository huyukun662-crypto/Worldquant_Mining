"""Round 55: test proven rv*accel*volwt structure across NON-USA regions.

Take R47/9q9o0zme winning structure (SH=2.33 on USA TOP3000):
  zscore(reverse(ts_decay_linear(multiply(multiply(
    ts_std_dev(returns, 20),
    subtract(returns, ts_delay(returns, 2))
  ), log(add(divide(volume, adv20), 1))), 25)))

5 region tests:
  DDD1 GLB / TOP3000  / SUBINDUSTRY
  DDD2 EUR / TOP2500  / SUBINDUSTRY
  DDD3 EUR / TOP1200  / SUBINDUSTRY (smaller, more liquid)
  DDD4 CHN / TOP2000U / SUBINDUSTRY (China A-shares)
  DDD5 ASI / MINVOL1M / SUBINDUSTRY (Asia)

If any region produces SH>=1.75 with full WQ-compliance, we have
region-diverse alphas to deliver.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r55")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(region: str, universe: str, neut: str = "SUBINDUSTRY", trunc: float = 0.05):
    return {
        "instrumentType": "EQUITY", "region": region, "universe": universe,
        "delay": 1, "decay": 8, "truncation": trunc, "neutralization": neut,
        "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
        "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
        "testPeriod": "P0Y0M",
    }


EXPRESSION = (
    "zscore(reverse(ts_decay_linear(multiply(multiply("
    "ts_std_dev(returns, 20), subtract(returns, ts_delay(returns, 2))"
    "), log(add(divide(volume, adv20), 1))), 25)))"
)

VARIANTS = [
    {"label": "DDD1_GLB_TOP3000", "settings": settings("GLB", "TOP3000")},
    {"label": "DDD2_EUR_TOP2500", "settings": settings("EUR", "TOP2500")},
    {"label": "DDD3_EUR_TOP1200", "settings": settings("EUR", "TOP1200")},
    {"label": "DDD4_CHN_TOP2000U", "settings": settings("CHN", "TOP2000U")},
    {"label": "DDD5_ASI_MINVOL1M", "settings": settings("ASI", "MINVOL1M")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_multi_region_r55_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "Test rv*accel*volwt structure across non-USA regions.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        s = v["settings"]
        log.info(f"  [{i}/5] {v['label']}: region={s['region']} universe={s['universe']} neut={s['neutralization']}")
        try:
            res = r5.submit(cm.session, EXPRESSION, s)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"],
                 "region": s["region"], "universe": s["universe"],
                 "neut": s["neutralization"], "trunc": s["truncation"],
                 "expression": EXPRESSION, **res}
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
    md = "# R55 multi-region test of rv*accel*volwt\n\n"
    md += f"Expression (fixed):\n```\n{EXPRESSION}\n```\n\n"
    md += ("| variant | region | universe | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---|---|---:|---:|---:|---|---|---|\n")
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
        md += (f"| {r['variant']} | {r['region']} | {r['universe']} | "
                f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | {r['fitness']:+.3f} | "
                f"{c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['region']} | {r['universe']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
