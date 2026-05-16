"""Round 88: cube transform broke SH to 1.23 but broke conc.

R87g signed_power(z, 3) + decay=15 -> SH +1.23 FIT +2.27, conc FAIL
(value 0.135 vs ~0.10 limit). This is the closest to gate so far.

Goal: keep cube's SH lift, suppress concentration. Try:

  R88a  cube + decay=25                 longer smooth -> lower conc
  R88b  cube + decay=30                 even longer
  R88c  cube + INDUSTRY neut             broader buckets
  R88d  cube + truncation=0.12           larger trunc cap
  R88e  signed_power(z, 2.5) decay=15    between square and cube
  R88f  cube + truncation=0.10           medium trunc
  R88g  cube + decay=15 + INDUSTRY       combine
  R88h  cube + decay=25 + INDUSTRY       triple-mitigation

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r88")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(neutralization: str = "SUBINDUSTRY", truncation: float = 0.08) -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": truncation,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


def MA60_pow(p) -> str:
    return f"signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), {p})"


cube = MA60_pow(3)
pow25 = MA60_pow(2.5)

VARIANTS = [
    {"label": "R88a_cube_decay25",          "expression": W(cube, 25),  "settings": settings()},
    {"label": "R88b_cube_decay30",          "expression": W(cube, 30),  "settings": settings()},
    {"label": "R88c_cube_IND_decay15",      "expression": W(cube, 15),  "settings": settings(neutralization="INDUSTRY")},
    {"label": "R88d_cube_trunc012",         "expression": W(cube, 15),  "settings": settings(truncation=0.12)},
    {"label": "R88e_p25_decay15",           "expression": W(pow25, 15), "settings": settings()},
    {"label": "R88f_cube_trunc010",         "expression": W(cube, 15),  "settings": settings(truncation=0.10)},
    {"label": "R88g_cube_d15_trunc015",     "expression": W(cube, 15),  "settings": settings(truncation=0.15)},
    {"label": "R88h_cube_IND_decay25",      "expression": W(cube, 25),  "settings": settings(neutralization="INDUSTRY")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r88_cube_conc_tame_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R88: tame the cube's concentration while keeping its SH lift.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], v["settings"])
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"],
                 "settings": v["settings"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} checks={res['checks_passed']}/{res['checks_total']}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT","LOW_SUB_UNIVERSE_SHARPE","SELF_CORRELATION"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")
    md = "# R88 tame cube concentration\n\n"
    md += ("| variant | neut | trunc | SH | TO | FIT | checks | conc | sub | sc | gate |\n"
           "|---|---|---:|---:|---:|---:|---|---|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        sc = next((c for c in r['checks'] if c['name']=='SELF_CORRELATION'), {})
        conc_ok = conc.get('result')=='PASS'
        sub_ok = sub.get('result')=='PASS'
        all_pass = (r['sharpe']>=1.25 and r['turnover']<0.20 and conc_ok and sub_ok)
        if all_pass: survivors.append(r)
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        s_ = r['settings']
        md += (f"| {r['variant']} | {s_['neutralization']} | {s_['truncation']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {sc.get('value','-')} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | - | - | FAIL | - | - | - | - | - | - | no |  "
               f"{r.get('error','?')[:80]}\n")
    md += f"\n**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS): {len(survivors)}/{len(results)}**\n"
    if survivors:
        md += "\n## Survivor expressions\n\n"
        for r in survivors:
            md += (f"### {r['variant']} -- alpha {r.get('alpha_id','?')}\n"
                   f"SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
                   f"FIT={r['fitness']:+.3f}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
