"""Round 118: BREAK GATE -- decay sweep on R117d/R117j near-winners.

R117 surfaced TWO near-winners (SH passes, TO just over):
  R117d MA3x2 + buyback decay=3
    SH +1.54 TO 0.278 conc+sub PASS SC 0.446 7/8 checks
    Need TO -0.08.
  R117j triple (MA3+tsrank+buyback) decay=3
    SH +1.39 TO 0.259 conc+sub PASS SC 0.457
    Need TO -0.06.

Sharpe/TO tradeoff per R113 sign-LDV frontier (0.05 SH per 0.03 TO):
  R117d decay 5 -> SH ~1.44 TO ~0.23 (close, still over)
  R117d decay 7 -> SH ~1.34 TO ~0.18 (PASS!)
  R117j decay 7 -> SH ~1.19 TO ~0.17 (TO PASS, SH borderline)

R118 focused decay sweep + compound platform decay on the two leads.

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r118")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(neutralization: str = "SUBINDUSTRY", decay: int = 8) -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": decay, "truncation": 0.08,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


# Components
def MA_CROSS_LDV(ma, d):
    return ("zscore(last_diff_value("
            f"sign(subtract(close, ts_mean(close, {ma}))), {d}))")

MA3 = MA_CROSS_LDV(3, 10)
BUYBACK = "zscore(reverse(divide(subtract(sharesout, ts_delay(sharesout, 252)), sharesout)))"
TSRANK = "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10)))"


def R117D(decay):
    return f"zscore(ts_decay_linear(add(multiply({MA3}, 2), {BUYBACK}), {decay}))"


def R117J(decay):
    return f"zscore(ts_decay_linear(add(add({MA3}, {TSRANK}), {BUYBACK}), {decay}))"


VARIANTS = [
    # R117d decay sweep
    {"label": "R118a_117d_decay5",  "expression": R117D(5)},
    {"label": "R118b_117d_decay6",  "expression": R117D(6)},
    {"label": "R118c_117d_decay7",  "expression": R117D(7)},

    # R117j (triple) decay sweep
    {"label": "R118d_117j_decay5",  "expression": R117J(5)},
    {"label": "R118e_117j_decay6",  "expression": R117J(6)},
    {"label": "R118f_117j_decay7",  "expression": R117J(7)},

    # R117d + platform decay (compound)
    {"label": "R118g_117d_d3_pf15",
     "expression": R117D(3),
     "settings": settings(decay=15)},
    {"label": "R118h_117d_d5_pf15",
     "expression": R117D(5),
     "settings": settings(decay=15)},

    # Weight variant (MA3 x1.5 + buyback) decay=5 (less SH heavy = lower TO)
    {"label": "R118i_ma3x15_buyback_d5",
     "expression": f"zscore(ts_decay_linear("
                   f"add(multiply({MA3}, 1.5), {BUYBACK}), 5))"},

    # R117j + platform decay
    {"label": "R118j_117j_d5_pf15",
     "expression": R117J(5),
     "settings": settings(decay=15)},
]

for v in VARIANTS:
    v.setdefault("settings", settings())


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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r118_decay_sweep_break_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R118: decay sweep on R117d (SH 1.54 TO 0.278) and R117j (SH 1.39 TO 0.259) "
        "to push TO below 0.20 gate while keeping SH > 1.25.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression'][:280]}")
        try:
            res = r5.submit(cm.session, v["expression"], v["settings"])
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"],
                 "settings": v["settings"], **res}
        if res.get("ok") and res.get("alpha_id"):
            time.sleep(3)
            try:
                sc_map = fetch_sc(cm.session, res["alpha_id"], max_wait=90)
                entry["sc_map"] = sc_map
                if sc_map:
                    log.info(f"      SC: {sc_map}")
            except Exception as e:
                log.warning(f"      SC fetch error: {e}")
        results.append(entry)
        try:
            (session_dir / "working" / "results_partial.json").write_text(
                json.dumps(results, indent=2))
        except Exception as e:
            log.warning(f"      partial write error: {e}")
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} checks={res['checks_passed']}/{res['checks_total']}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT","LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:200]}")
    md = "# R118 decay sweep break gate\n\n"
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
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | - | no | - |"
               f" {r.get('error','?')[:120]}\n")
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
