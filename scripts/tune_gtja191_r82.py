"""Round 82: stack R81 wins -- cube + INDUSTRY + trunc + composites.

R81 highlights:
  R81a VWAPmom cube + zscore-IN     SH +1.28  FIT +2.68  CONC FAIL 0.307
  R81g VWAPmom PV6 + decay 60       SH +1.02  FIT +1.55  CONC FAIL 0.102 (just over)
  R81b VWAPmom PV6 + INDUSTRY       SH +1.00  FIT +1.54  CONC + SUB PASS!  (6/8)

R82 strategies:

  R82a  R81a cube + trunc 0.03                    fix conc on cube
  R82b  R81a cube + INDUSTRY + trunc 0.03         max constrain on cube
  R82c  VWAPmom pow 2.5 + INDUSTRY                 mid amp
  R82d  VWAPmom_PV6 x G62 composite (mult)
  R82e  rank composite then PV6
  R82f  VWAPmom cube + decay 60                    longer smoothing
  R82g  VWAPmom PV6 + TOP1000 universe             tighter universe
  R82h  VWAPmom PV6 + ts_zscore time-series wrap   alt outer

Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7.
DO NOT auto-submit -- verify manually.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r82")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(truncation: float = 0.08,
             neutralization: str = "SUBINDUSTRY",
             universe: str = "TOP3000") -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": universe,
        "delay": 1, "decay": 8, "truncation": truncation,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


VWAP_RET20 = "divide(subtract(vwap, ts_delay(vwap, 20)), ts_delay(vwap, 20))"
VWAP_BASE = f"reverse({VWAP_RET20})"
G62 = "multiply(-1, ts_corr(high, rank(volume), 5))"

CUBE = f"signed_power(zscore({VWAP_BASE}), 3)"
PV6 = f"signed_power(zscore({VWAP_BASE}), 2)"
POW25 = f"signed_power(zscore({VWAP_BASE}), 2.5)"

R82a = W(CUBE)                                      # cube + trunc 0.03 via settings
R82b = W(CUBE)                                      # cube + INDUSTRY + trunc 0.03
R82c = W(POW25)                                     # 2.5 + INDUSTRY
R82d = W(f"multiply({PV6}, {G62})")                 # composite mult
R82e = W(f"signed_power(zscore(add({VWAP_BASE}, {G62})), 2)")  # additive then PV6
R82f = W(CUBE, decay=60)                            # cube + D60
R82g = W(PV6)                                       # PV6 + TOP1000
R82h = f"ts_zscore({W(PV6)}, 60)"                   # PV6 wrapped in ts_zscore outer


VARIANTS = [
    {"label": "R82a_cube_tr03",          "expression": R82a, "settings": settings(truncation=0.03)},
    {"label": "R82b_cube_IND_tr03",      "expression": R82b, "settings": settings(truncation=0.03, neutralization="INDUSTRY")},
    {"label": "R82c_pow25_IND",          "expression": R82c, "settings": settings(neutralization="INDUSTRY")},
    {"label": "R82d_PV6_x_G62",          "expression": R82d, "settings": settings()},
    {"label": "R82e_add_then_PV6",       "expression": R82e, "settings": settings()},
    {"label": "R82f_cube_D60",           "expression": R82f, "settings": settings()},
    {"label": "R82g_PV6_TOP1000",        "expression": R82g, "settings": settings(universe="TOP1000")},
    {"label": "R82h_PV6_ts_z60_outer",   "expression": R82h, "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r82_vwapmom_stack_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R82: stack R81 wins (cube + INDUSTRY + trunc + composites).\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        log.info(f"      univ={v['settings']['universe']} trunc={v['settings']['truncation']} neut={v['settings']['neutralization']}")
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
    md = "# R82 stack R81 wins\n\n"
    md += ("| variant | univ | trunc | neut | SH | TO | FIT | checks | conc | sub | sc | gate |\n"
           "|---|---|---:|---|---:|---:|---:|---|---|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        sc = next((c for c in r['checks'] if c['name']=='SELF_CORRELATION'), {})
        conc_ok = conc.get('result')=='PASS'
        sub_ok = sub.get('result')=='PASS'
        all_pass = (r['sharpe']>=1.5 and r['turnover']<0.20 and conc_ok and sub_ok)
        if all_pass: survivors.append(r)
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        s_ = r['settings']
        md += (f"| {r['variant']} | {s_['universe']} | {s_['truncation']} | {s_['neutralization']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {sc.get('value','-')} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | - | - | - | FAIL | - | - | - | - | - | - | no |  "
               f"{r.get('error','?')[:80]}\n")
    md += f"\n**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): {len(survivors)}/{len(results)}**\n"
    if survivors:
        md += "\n## Survivor expressions\n\n"
        for r in survivors:
            md += (f"### {r['variant']} -- alpha {r.get('alpha_id','?')}\n"
                   f"SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
                   f"FIT={r['fitness']:+.3f}\n"
                   f"settings: {json.dumps({k:v for k,v in r['settings'].items() if k in ('universe','truncation','neutralization')})}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
