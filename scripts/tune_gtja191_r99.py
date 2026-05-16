"""Round 99: bracket-search the close-MA60 p-exponent and tame conc.

Close-based MA60 family is structurally orthogonal to portfolio
(R86c SC=0.12 vs A1nnxAdw, R88e SC=0.20). The blocker is conc.

Conc/SH bracket from prior rounds:
  p=2.5 d=15 (R88e, WjNG1Q9j)  SH 1.15  conc PASS (~0.08)
  p=2.7 d=15 (R90d, RRN8QGja)  SH 1.29  conc FAIL (0.110)
  p=2.7 d=15 t=0.12 (R90e)     SH 1.37  conc FAIL (0.127)
  p=2.8 d=10 (R90g)             SH 1.25  conc FAIL (0.117)

R99 targets the gap p in [2.5, 2.7]:
  R99a  p=2.6 d=15                              tip-of-iceberg
  R99b  p=2.65 d=15                             midpoint
  R99c  p=2.7 d=18                              same p, more decay
  R99d  p=2.7 d=20                              even more decay
  R99e  add(p27_d15, MA20_PV6) blend            dilute via MA20
  R99f  p=2.7 d=15 INDUSTRY                     broader neut
  R99g  p=2.7 d=15 trunc=0.07                   tighter cap
  R99h  p=2.7 d=22                              very smooth

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7 vs A1nnxAdw.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r99")
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


def MA_pow(p, n: int = 60) -> str:
    return f"signed_power(zscore(reverse(divide(close, ts_mean(close, {n})))), {p})"


p26 = MA_pow(2.6)
p265 = MA_pow(2.65)
p27 = MA_pow(2.7)
ma20_pv6 = MA_pow(2, 20)

VARIANTS = [
    {"label": "R99a_p26_d15",         "expression": W(p26, 15), "settings": settings()},
    {"label": "R99b_p265_d15",        "expression": W(p265, 15),"settings": settings()},
    {"label": "R99c_p27_d18",         "expression": W(p27, 18), "settings": settings()},
    {"label": "R99d_p27_d20",         "expression": W(p27, 20), "settings": settings()},
    {"label": "R99e_p27_plus_ma20",   "expression": W(f"add({p27}, {ma20_pv6})", 15), "settings": settings()},
    {"label": "R99f_p27_d15_IND",     "expression": W(p27, 15), "settings": settings(neutralization="INDUSTRY")},
    {"label": "R99g_p27_d15_t007",    "expression": W(p27, 15), "settings": settings(truncation=0.07)},
    {"label": "R99h_p27_d22",         "expression": W(p27, 22), "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r99_close_bracket_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R99: bracket-search p in [2.6, 2.7] on MA60 with conc-taming.\n"
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
                log.info(f"      SC: pending (queue full)")
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
    md = "# R99 close-MA60 bracket\n\n"
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
