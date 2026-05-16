"""Round 102: ultra-fine interp + blend close x Parkinson.

R101 closest:
  R101b p=2.7 d=15 t=0.087  SH 1.23 conc PASS  (-0.02 SH from gate)
  R101f p=2.7 d=12 t=0.085  SH 1.25 conc FAIL 0.103
  R101g p=2.7 d=10 t=0.090  SH 1.28 conc FAIL 0.113

R102 paths:
  (1) interp between R101b PASS and R101f FAIL
  (2) blend p27_close + Parkinson (R95a) -- both low-individual-SH-vs-portfolio

  R102a  p=2.7 d=14 t=0.086             interp
  R102b  p=2.7 d=13 t=0.086             interp
  R102c  p=2.7 d=14 t=0.087             interp
  R102d  p=2.7 d=15 t=0.088             interp
  R102e  add(p27_close, R95a_park)       50/50 blend
  R102f  add(p27_close*2, R95a_park)     close-weighted blend (~67/33)
  R102g  add(p27_close, R95a_park*2)     park-weighted blend (~33/67)
  R102h  add(R88e_p25, R95a_park)        p25_close + park blend (R88e safer conc)

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r102")
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


# Parkinson core (R95a structure inner)
PARK_CORE = "zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60)))"

p25_close = MA60_pow(2.5)
p27_close = MA60_pow(2.7)


def mul_constant(x: str, k: float) -> str:
    return f"multiply({x}, {k})"


VARIANTS = [
    {"label": "R102a_p27_d14_t0086",   "expression": W(p27_close, 14),
        "settings": settings(truncation=0.086)},
    {"label": "R102b_p27_d13_t0086",   "expression": W(p27_close, 13),
        "settings": settings(truncation=0.086)},
    {"label": "R102c_p27_d14_t0087",   "expression": W(p27_close, 14),
        "settings": settings(truncation=0.087)},
    {"label": "R102d_p27_d15_t0088",   "expression": W(p27_close, 15),
        "settings": settings(truncation=0.088)},
    {"label": "R102e_blend_close_park", "expression": W(f"add({p27_close}, {PARK_CORE})", 15),
        "settings": settings()},
    {"label": "R102f_close2x_park1x",   "expression": W(f"add({mul_constant(p27_close, 2)}, {PARK_CORE})", 15),
        "settings": settings()},
    {"label": "R102g_close1x_park2x",   "expression": W(f"add({p27_close}, {mul_constant(PARK_CORE, 2)})", 15),
        "settings": settings()},
    {"label": "R102h_p25close_park",    "expression": W(f"add({p25_close}, {PARK_CORE})", 15),
        "settings": settings()},
]


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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r102_interp_blend_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R102: interp R101b/f + blend close_p27 with Parkinson.\n"
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
    md = "# R102 interp + blend\n\n"
    md += ("| variant | trunc | SH | TO | FIT | checks | conc | conc_val | sub | max_SC | gate | alpha_id |\n"
           "|---|---:|---:|---:|---:|---|---|---|---|---|---|---|\n")
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
        c = "P" if conc_ok else "FAIL"
        cv = conc.get('value', '-')
        cv_str = f"{cv:.4f}" if isinstance(cv, (int, float)) else "-"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        scd = f"{max_sc:.3f}" if max_sc is not None else "pending"
        tag = "**YES**" if all_pass else "no"
        s_ = r['settings']
        md += (f"| {r['variant']} | {s_['truncation']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {cv_str} | {s} | {scd} | {tag} | {r.get('alpha_id','-')} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | - | FAIL | - | - | - | - | - | - | - | no | - | "
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
