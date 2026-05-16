"""Round 98: amplify SH on the LOW-SC vol-delta angle from R97.

R97f delta(RV,5) linear was SC=0.22 (orthogonal to A1nnxAdw) but SH=0.01.
If we add nonlinearity (PV6/p=2.5) we may unlock SH while keeping low SC.

Also fix R97c/d unit errors by using multiply(x,x) instead of power(x,2)
where x is unitless-required.

  R98a  delta(RV, 5) + PV6 rev                       core hypothesis
  R98b  delta(RV, 10) + PV6 rev                      slower delta
  R98c  delta(Parkinson, 5) + PV6 rev                Parkinson delta
  R98d  delta(RV, 5) + p=2.5 rev                     stronger nonlin
  R98e  semi-var ratio fixed unit                    asymmetry signal
  R98f  vol-volume corr fixed unit                   multi-field coupling
  R98g  industry-relative RV + PV6 rev                broader R97e
  R98h  cross-sec rank of vol: rank(RV) reversed     rank-based

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7 vs A1nnxAdw.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r98")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(neutralization: str = "SUBINDUSTRY") -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": 0.08,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 15) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


def pv6_rev(signal: str) -> str:
    return f"signed_power(zscore(reverse({signal})), 2)"


def p25_rev(signal: str) -> str:
    return f"signed_power(zscore(reverse({signal})), 2.5)"


RV = "ts_std_dev(returns, 60)"
PARK = "ts_mean(power(log(divide(high, low)), 2), 60)"

# unit-safe semi-variance: multiply(x,x) instead of power(x,2)
UPVOL = "ts_mean(multiply(max(returns, 0), max(returns, 0)), 60)"
DNVOL = "ts_mean(multiply(min(returns, 0), min(returns, 0)), 60)"
SEMI_RATIO = f"divide({UPVOL}, add({DNVOL}, 0.0001))"

# unit-safe vol-volume corr
RET_SQ = "multiply(returns, returns)"
VV_CORR = f"ts_corr({RET_SQ}, volume, 60)"

# delta-vol structures
DRV5 = f"subtract({RV}, ts_delay({RV}, 5))"
DRV10 = f"subtract({RV}, ts_delay({RV}, 10))"
DPARK5 = f"subtract({PARK}, ts_delay({PARK}, 5))"

# industry-relative vol
IND_REL_VOL = f"divide({RV}, group_mean({RV}, 1, industry))"

VARIANTS = [
    {"label": "R98a_drv5_PV6_rev",      "expression": W(pv6_rev(DRV5), 15),    "settings": settings()},
    {"label": "R98b_drv10_PV6_rev",     "expression": W(pv6_rev(DRV10), 15),   "settings": settings()},
    {"label": "R98c_dpark5_PV6_rev",    "expression": W(pv6_rev(DPARK5), 15),  "settings": settings()},
    {"label": "R98d_drv5_p25_rev",      "expression": W(p25_rev(DRV5), 15),    "settings": settings()},
    {"label": "R98e_semi_var_ratio",    "expression": W(f"zscore({SEMI_RATIO})", 15), "settings": settings()},
    {"label": "R98f_vol_volume_corr",   "expression": W(f"zscore({VV_CORR})", 15),    "settings": settings()},
    {"label": "R98g_ind_rel_vol_PV6",   "expression": W(pv6_rev(IND_REL_VOL), 15),    "settings": settings()},
    {"label": "R98h_rank_RV_rev",       "expression": W(f"zscore(reverse(rank({RV})))", 15), "settings": settings()},
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def fetch_sc(session, alpha_id: str, max_wait: int = 60):
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self"
    t0 = time.time()
    while time.time() - t0 < max_wait:
        r = session.get(url)
        if r.status_code == 200 and r.text:
            try:
                data = r.json()
                records = data.get('records', [])
                return {rec[0]: rec[5] for rec in records}
            except Exception:
                pass
        time.sleep(2)
    return {}


def main():
    r5 = _load(REPO / "scripts" / "run_5agent_workflow.py", "r5")
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r98_drv_orthogonal_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R98: delta-vol + nonlinearity (low SC), fixed unit semi-var + vol-vol corr.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression'][:150]}...")
        try:
            res = r5.submit(cm.session, v["expression"], v["settings"])
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"],
                 "settings": v["settings"], **res}
        if res.get("ok") and res.get("alpha_id"):
            time.sleep(3)
            sc_map = fetch_sc(cm.session, res["alpha_id"])
            entry["sc_map"] = sc_map
            if sc_map:
                log.info(f"      SC: {sc_map}")
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} checks={res['checks_passed']}/{res['checks_total']}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT","LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")
    md = "# R98 delta-vol + nonlin + unit-fixed\n\n"
    md += ("| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate |\n"
           "|---|---:|---:|---:|---|---|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        conc_ok = conc.get('result')=='PASS'
        sub_ok = sub.get('result')=='PASS'
        sc_map = r.get('sc_map', {})
        max_sc = max((abs(v) for v in sc_map.values() if v is not None), default=None)
        sc_ok = max_sc is None or max_sc < 0.7
        all_pass = (r['sharpe']>=1.25 and r['turnover']<0.20 and conc_ok and sub_ok and sc_ok)
        if all_pass: survivors.append(r)
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        scd = f"{max_sc:.3f}" if max_sc is not None else "?"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {scd} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | - | no |  "
               f"{r.get('error','?')[:80]}\n")
    md += f"\n**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7): {len(survivors)}/{len(results)}**\n"
    if survivors:
        md += "\n## Survivor expressions\n\n"
        for r in survivors:
            md += (f"### {r['variant']} -- alpha {r.get('alpha_id','?')}\n"
                   f"SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
                   f"FIT={r['fitness']:+.3f} SC={r.get('sc_map',{})}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
