"""Round 100: micro-search p in [2.66, 2.69] + truncation lever to find
the exact conc-PASS / SH-pass intersection.

R99 confirmed close-based MA60 family has low SC (~0.39 vs A1nnxAdw).
But cliff between p=2.65 (SH 1.17 conc PASS) and p=2.70 (SH 1.29 conc FAIL).
Need to find what's between, or use truncation to force conc PASS at p=2.7.

  R100a  p=2.66 d=15                            micro p
  R100b  p=2.67 d=15
  R100c  p=2.68 d=15
  R100d  p=2.69 d=15
  R100e  p=2.7  d=15 truncation=0.10            cap weight at 10%
  R100f  p=2.7  d=15 truncation=0.09            tighter cap
  R100g  add(p27, MA60_linear_rev) blend         dilute via linear MA60
  R100h  p=2.7  d=15 INDUSTRY truncation=0.10    combo

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r100")
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


MA60_lin = "zscore(reverse(divide(close, ts_mean(close, 60))))"
p27 = MA60_pow(2.7)

VARIANTS = [
    {"label": "R100a_p266_d15",          "expression": W(MA60_pow(2.66), 15), "settings": settings()},
    {"label": "R100b_p267_d15",          "expression": W(MA60_pow(2.67), 15), "settings": settings()},
    {"label": "R100c_p268_d15",          "expression": W(MA60_pow(2.68), 15), "settings": settings()},
    {"label": "R100d_p269_d15",          "expression": W(MA60_pow(2.69), 15), "settings": settings()},
    {"label": "R100e_p27_d15_t010",      "expression": W(p27, 15), "settings": settings(truncation=0.10)},
    {"label": "R100f_p27_d15_t009",      "expression": W(p27, 15), "settings": settings(truncation=0.09)},
    {"label": "R100g_p27_plus_lin_MA60", "expression": W(f"add({p27}, {MA60_lin})", 15), "settings": settings()},
    {"label": "R100h_p27_IND_t010",      "expression": W(p27, 15), "settings": settings(neutralization="INDUSTRY", truncation=0.10)},
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def fetch_sc(session, alpha_id: str, max_wait: int = 120):
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r100_micro_close_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R100: micro-search p in [2.66,2.69] + truncation lever on MA60 close-based.\n"
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
            sc_map = fetch_sc(cm.session, res["alpha_id"], max_wait=120)
            entry["sc_map"] = sc_map
            if sc_map:
                log.info(f"      SC: {sc_map}")
            else:
                log.info(f"      SC: pending")
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
    md = "# R100 micro-bracket + trunc lever\n\n"
    md += ("| variant | neut | trunc | SH | TO | FIT | checks | conc | sub | max_SC | gate | alpha_id |\n"
           "|---|---|---:|---:|---:|---:|---|---|---|---|---|---|\n")
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
        s_ = r['settings']
        md += (f"| {r['variant']} | {s_['neutralization']} | {s_['truncation']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {scd} | {tag} | {r.get('alpha_id','-')} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | - | - | FAIL | - | - | - | - | - | - | no | - | "
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
