"""Round 95: tame Parkinson/Rogers-Satchell vol's concentration.

R94 breakthrough:
  R94a Parkinson vol mean-rev p=2.5      SH +2.02  FIT +7.10  conc FAIL (0.31)
  R94b Rogers-Satchell mean-rev p=2.5    SH +1.75  FIT +5.56  conc FAIL (0.31)

Same SH/conc trade-off as MA60 but starting from much higher SH.
Even a 30-40% SH drop after taming would land safely above 1.25 gate.

  R95a  Parkinson + linear zscore (no power)              maximum tame
  R95b  Parkinson + PV6 (p=2)                              moderate tame
  R95c  Parkinson + p=2.5 + decay=30                       more smoothing
  R95d  Parkinson + p=2.5 + truncation=0.04                tighter cap
  R95e  Parkinson + p=2.5 + INDUSTRY                       broader neut
  R95f  Rogers-Satchell + PV6 (p=2)                        same on RS
  R95g  Rogers-Satchell + p=2.5 + INDUSTRY                 INDUSTRY on RS
  R95h  Parkinson 20d window + p=2.5                       shorter base

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r95")
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


def W(core: str, decay: int = 15) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


def PV(z_core: str, p: float) -> str:
    return f"signed_power(zscore({z_core}), {p})"


# Parkinson vol = mean of (ln H/L)^2 over n days
def parkinson(n: int = 60) -> str:
    return f"ts_mean(power(log(divide(high, low)), 2), {n})"


# Rogers-Satchell vol = mean of ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O) over n days
def rs_vol(n: int = 60) -> str:
    return (f"ts_mean(add(multiply(log(divide(high, close)), log(divide(high, open))), "
            f"multiply(log(divide(low, close)), log(divide(low, open)))), {n})")


PARK = parkinson(60)
PARK20 = parkinson(20)
RS = rs_vol(60)

VARIANTS = [
    {"label": "R95a_park_linear_d15",      "expression": W(f"zscore(reverse({PARK}))", 15),
        "settings": settings()},
    {"label": "R95b_park_PV6_d15",         "expression": W(PV(f"reverse({PARK})", 2),   15),
        "settings": settings()},
    {"label": "R95c_park_p25_d30",         "expression": W(PV(f"reverse({PARK})", 2.5), 30),
        "settings": settings()},
    {"label": "R95d_park_p25_d15_t004",    "expression": W(PV(f"reverse({PARK})", 2.5), 15),
        "settings": settings(truncation=0.04)},
    {"label": "R95e_park_p25_d15_IND",     "expression": W(PV(f"reverse({PARK})", 2.5), 15),
        "settings": settings(neutralization="INDUSTRY")},
    {"label": "R95f_rs_PV6_d15",           "expression": W(PV(f"reverse({RS})", 2),     15),
        "settings": settings()},
    {"label": "R95g_rs_p25_d15_IND",       "expression": W(PV(f"reverse({RS})", 2.5),   15),
        "settings": settings(neutralization="INDUSTRY")},
    {"label": "R95h_park20_p25_d15",       "expression": W(PV(f"reverse({PARK20})", 2.5), 15),
        "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r95_tame_vol_estimators_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R95: tame Parkinson/Rogers-Satchell vol estimators (SH 2.02/1.75 but conc FAIL).\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression'][:140]}...")
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
    md = "# R95 tame vol estimators\n\n"
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
