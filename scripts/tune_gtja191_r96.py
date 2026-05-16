"""Round 96: find vol-rev alpha with LOW SC vs A1nnxAdw (BB-GK, uses ln(H/L)).

R95a Parkinson + linear:
  SH 1.30 conc PASS GATE-PASS  -- but SC=0.87 vs A1nnxAdw -- BLOCKED

Both Parkinson and GK rely on ln(H/L)^2 -> high SC. Need vol estimators
that diversify away from pure H/L:
  - Rogers-Satchell (uses H/L/C/O multiplicatively)
  - realized vol (uses returns, not H/L)
  - Yang-Zhang (combines overnight + intraday)
  - vol-of-vol (second-order)

  R96a  Rogers-Satchell + linear (no power)            H/L/C/O mix
  R96b  realized vol (returns-based) + linear           pure returns
  R96c  Yang-Zhang vol estimator                        comprehensive
  R96d  Vol-of-vol returns: std(std(ret,5), 60)         second-order
  R96e  Parkinson 20d + linear                          different window
  R96f  Parkinson 120d + linear                         longer window
  R96g  Range expansion (H-L)/C linear                  non-squared
  R96h  RS + PV6 (p=2)                                  RS with mild power

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS. DO NOT auto-submit.
Survivors must additionally have SC vs A1nnxAdw < 0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r96")
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


def linear_rev(signal: str) -> str:
    return f"zscore(reverse({signal}))"


def pv6_rev(signal: str) -> str:
    return f"signed_power(zscore(reverse({signal})), 2)"


# Rogers-Satchell vol = mean of ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O)
RS = ("ts_mean(add(multiply(log(divide(high, close)), log(divide(high, open))), "
      "multiply(log(divide(low, close)), log(divide(low, open)))), 60)")

# Realized vol = std of returns
RV = "ts_std_dev(returns, 60)"

# Yang-Zhang ~ overnight vol + intraday vol. Simplified:
# overnight = ts_mean((ln(open/prev_close))^2, 60), intraday = ts_mean((ln(C/O))^2, 60)
YZ = ("add(ts_mean(power(log(divide(open, ts_delay(close, 1))), 2), 60), "
      "ts_mean(power(log(divide(close, open)), 2), 60))")

# Vol of vol
VOV = "ts_std_dev(ts_std_dev(returns, 5), 60)"

# Parkinson with different windows
PARK20 = "ts_mean(power(log(divide(high, low)), 2), 20)"
PARK120 = "ts_mean(power(log(divide(high, low)), 2), 120)"

# Range expansion (non-squared)
RANGE = "ts_mean(divide(subtract(high, low), close), 60)"

VARIANTS = [
    {"label": "R96a_rs_linear",        "expression": W(linear_rev(RS),     15), "settings": settings()},
    {"label": "R96b_rv_linear",        "expression": W(linear_rev(RV),     15), "settings": settings()},
    {"label": "R96c_yz_linear",        "expression": W(linear_rev(YZ),     15), "settings": settings()},
    {"label": "R96d_vov_linear",       "expression": W(linear_rev(VOV),    15), "settings": settings()},
    {"label": "R96e_park20_linear",    "expression": W(linear_rev(PARK20), 15), "settings": settings()},
    {"label": "R96f_park120_linear",   "expression": W(linear_rev(PARK120),15), "settings": settings()},
    {"label": "R96g_range_linear",     "expression": W(linear_rev(RANGE),  15), "settings": settings()},
    {"label": "R96h_rs_PV6",           "expression": W(pv6_rev(RS),        15), "settings": settings()},
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def fetch_sc(session, alpha_id: str, max_wait: int = 60):
    """Poll /correlations/self until non-empty, return dict {target_id: corr}."""
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r96_low_sc_vol_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R96: find vol mean-rev alpha with SC < 0.7 vs A1nnxAdw (BB-GK).\n"
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
        # poll SC if the alpha was created
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
    md = "# R96 low-SC vol mean-rev hunt\n\n"
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
