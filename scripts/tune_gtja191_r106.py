"""Round 106: explore the blend frontier with diverse vol estimators
and triple-blends. Push SH beyond R102g 1.51.

R102/R105 found 6 gate-pass blends, all close + vol_estimator pattern.
Park and C9 are interchangeable -> same vol factor.

  R106a  close + Rogers-Satchell linear x2          new vol type
  R106b  close + Yang-Zhang linear x2               YZ vol
  R106c  close + (H-L)/C linear x2                  range/C
  R106d  close + RV (std(returns,60)) x2            realized vol
  R106e  close + park + C9 (triple)                 multi-vol
  R106f  close + park x3 (more park)                push park weight
  R106g  close x0.5 + park x2 (close diluted)       less close
  R106h  close + park x2 + decay=10 (faster decay)  decay sweep

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r106")
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


def mulk(x, k):
    return f"multiply({x}, {k})"


# close component
P27 = "signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7)"

# vol estimators (linear-reverse z-score)
PARK = "zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60)))"
RS = ("zscore(reverse(ts_mean(add(multiply(log(divide(high, close)), log(divide(high, open))), "
      "multiply(log(divide(low, close)), log(divide(low, open)))), 60)))")
YZ = ("zscore(reverse(add(ts_mean(power(log(divide(open, ts_delay(close, 1))), 2), 60), "
      "ts_mean(power(log(divide(close, open)), 2), 60))))")
RANGE_C = "zscore(reverse(ts_mean(divide(subtract(high, low), close), 60)))"
RV = "zscore(reverse(ts_std_dev(returns, 60)))"
C9 = "zscore(reverse(ts_std_dev(divide(close, vwap), 60)))"

VARIANTS = [
    {"label": "R106a_close_RSx2",           "expression": W(f"add({P27}, {mulk(RS, 2)})", 15)},
    {"label": "R106b_close_YZx2",           "expression": W(f"add({P27}, {mulk(YZ, 2)})", 15)},
    {"label": "R106c_close_rangeCx2",       "expression": W(f"add({P27}, {mulk(RANGE_C, 2)})", 15)},
    {"label": "R106d_close_RVx2",           "expression": W(f"add({P27}, {mulk(RV, 2)})", 15)},
    {"label": "R106e_close_park_C9_triple", "expression": W(f"add(add({P27}, {PARK}), {C9})", 15)},
    {"label": "R106f_close_parkx3",         "expression": W(f"add({P27}, {mulk(PARK, 3)})", 15)},
    {"label": "R106g_close05x_parkx2",      "expression": W(f"add({mulk(P27, 0.5)}, {mulk(PARK, 2)})", 15)},
    {"label": "R106h_close_parkx2_d10",     "expression": W(f"add({P27}, {mulk(PARK, 2)})", 10)},
]
for v in VARIANTS:
    v["settings"] = settings()


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def fetch_sc(session, alpha_id: str, max_wait: int = 90):
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self"
    t0 = time.time()
    while time.time() - t0 < max_wait:
        r = session.get(url)
        if r.status_code == 200 and r.text and len(r.text) > 50:
            try:
                data = r.json()
                records = data.get('records', [])
                if records:
                    return {rec[0]: rec[5] for rec in records}
            except Exception:
                pass
        time.sleep(3)
    return {}


def main():
    r5 = _load(REPO / "scripts" / "run_5agent_workflow.py", "r5")
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r106_blend_frontier_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R106: blend frontier -- diverse vol estimators + triple + push park weight.\n"
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
            sc_map = fetch_sc(cm.session, res["alpha_id"], max_wait=90)
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
    md = "# R106 blend frontier\n\n"
    md += ("| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate | alpha_id |\n"
           "|---|---:|---:|---:|---|---|---|---|---|---|\n")
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
        scd = f"{max_sc:.3f}" if max_sc is not None else "pending"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {scd} | {tag} | {r.get('alpha_id','-')} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | - | no | - | "
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
