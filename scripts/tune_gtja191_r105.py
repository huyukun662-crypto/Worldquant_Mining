"""Round 105: exploit R104 cold-core leads. 3 threads:

Thread A: C9 vwap_dispersion is the new Parkinson (SH 1.83 SC 0.89).
  Blend with close-MA60 (R102g pattern) -- expect SH 1.5+ with SC ~0.5.

Thread B: C2 days_since_low + C4 close_vwap_drift each give SH 1.0 SC 0.11
  under 3-tier outer. Try adding signed_power outer to push past gate.

Thread C: C9 linear (z(reverse(C9)) no power) -- intermediate point.

  R105a  blend(close_p27, C9_zscore_reverse)x2_close       2:1 blend
  R105b  blend(close_p27, C9_zscore_reverse)1:1            equal blend
  R105c  blend(close_p27, C9_zscore_reverse)x2_C9          1:2 blend (R102g analog)
  R105d  C2 + p=2.5 outer                                   nonlin boost C2
  R105e  C4 + p=2.5 outer                                   nonlin boost C4
  R105f  C9 linear (no power, no 3-tier)                    intermediate test
  R105g  blend(close_p27, C2_zscore_reverse) 1:1            C2 blend
  R105h  blend(close_p27, C4_zscore_reverse) 1:1            C4 blend

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r105")
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


def MA60_pow(p) -> str:
    return f"signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), {p})"


def mulk(x, k):
    return f"multiply({x}, {k})"


# cold cores
C2 = "ts_arg_min(close, 60)"
C4 = "ts_mean(divide(close, vwap), 60)"
C9 = "ts_std_dev(divide(close, vwap), 60)"

# linear-reverse z of cold cores
C9_zr = f"zscore(reverse({C9}))"
C2_zr = f"zscore(reverse({C2}))"
C4_zr = f"zscore(reverse({C4}))"

p27 = MA60_pow(2.7)


def pv25_rev(signal: str) -> str:
    return f"signed_power(zscore(reverse({signal})), 2.5)"


VARIANTS = [
    {"label": "R105a_close2x_C9x1",  "expression": W(f"add({mulk(p27, 2)}, {C9_zr})", 15)},
    {"label": "R105b_close1x_C9x1",  "expression": W(f"add({p27}, {C9_zr})", 15)},
    {"label": "R105c_close1x_C9x2",  "expression": W(f"add({p27}, {mulk(C9_zr, 2)})", 15)},
    {"label": "R105d_C2_p25_outer",  "expression": W(pv25_rev(C2), 15)},
    {"label": "R105e_C4_p25_outer",  "expression": W(pv25_rev(C4), 15)},
    {"label": "R105f_C9_linear",     "expression": W(C9_zr, 15)},
    {"label": "R105g_close1x_C2x1",  "expression": W(f"add({p27}, {C2_zr})", 15)},
    {"label": "R105h_close1x_C4x1",  "expression": W(f"add({p27}, {C4_zr})", 15)},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r105_exploit_cold_leads_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R105: exploit R104 cold-core leads -- 3 threads (C9 blend, C2/C4 nonlin, C9 linear).\n"
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
    md = "# R105 exploit cold leads\n\n"
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
