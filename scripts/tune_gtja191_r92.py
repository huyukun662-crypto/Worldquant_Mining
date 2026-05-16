"""Round 92: winsorize-then-power -- the cheat-sheet lever.

From the consultant cheat sheet (BV1LXRMBHEbR):
  winsorize -- 3-5 sigma truncation, listed alongside zscore as a
  data preprocessing operator.

Hypothesis: winsorize the z-scored signal BEFORE power transform.
The cube's SH lift comes from extreme tail values; winsorizing
caps those tails -> SH lift preserved but per-stock weight bounded
-> conc PASS while keeping SH > 1.25.

  R92a  winsorize(z, std=3.5) + p=3 cube                THE KEY TEST
  R92b  winsorize(z, std=2.5) + p=3 cube                tight clip
  R92c  winsorize(z, std=4.0) + p=3 cube                loose clip
  R92d  winsorize(z, std=3.0) + p=2.5                   p=2.5 baseline + winsor
  R92e  outer winsorize: winsorize(cube, std=3.5)        post-clip
  R92f  winsorize(z, std=3) + p=2.7
  R92g  winsorize(z, std=3) + p=2.8
  R92h  winsorize(z, std=2.5) + p=3 + decay=10           tight + faster

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r92")
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


# inner z-score on raw MA60 reversion signal
Z_INNER = "zscore(reverse(divide(close, ts_mean(close, 60))))"


def winsor_pow(std: float, p: float) -> str:
    return f"signed_power(winsorize({Z_INNER}, std={std}), {p})"


def outer_winsor_pow(std: float, p: float) -> str:
    return f"winsorize(signed_power({Z_INNER}, {p}), std={std})"


VARIANTS = [
    {"label": "R92a_wsr35_p3_d15",    "expression": W(winsor_pow(3.5, 3),   15), "settings": settings()},
    {"label": "R92b_wsr25_p3_d15",    "expression": W(winsor_pow(2.5, 3),   15), "settings": settings()},
    {"label": "R92c_wsr40_p3_d15",    "expression": W(winsor_pow(4.0, 3),   15), "settings": settings()},
    {"label": "R92d_wsr30_p25_d15",   "expression": W(winsor_pow(3.0, 2.5), 15), "settings": settings()},
    {"label": "R92e_outer_wsr35_p3",  "expression": W(outer_winsor_pow(3.5, 3), 15), "settings": settings()},
    {"label": "R92f_wsr30_p27_d15",   "expression": W(winsor_pow(3.0, 2.7), 15), "settings": settings()},
    {"label": "R92g_wsr30_p28_d15",   "expression": W(winsor_pow(3.0, 2.8), 15), "settings": settings()},
    {"label": "R92h_wsr25_p3_d10",    "expression": W(winsor_pow(2.5, 3),   10), "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r92_winsorize_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R92: winsorize-then-power test -- can winsorize tame cube's conc?\n"
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
    md = "# R92 winsorize-then-power\n\n"
    md += ("| variant | SH | TO | FIT | checks | conc | sub | sc | gate |\n"
           "|---|---:|---:|---:|---|---|---|---|---|\n")
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
        md += (f"| {r['variant']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {sc.get('value','-')} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | - | no |  "
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
