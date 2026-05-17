"""Round 114: push R113b (sign-LDV+decay3) past TO gate with diverse cutters.

R113 frontier on sign-LDV (positive sign, unreversed):
  decay=0   SH 1.72  TO 0.603  (R113a)
  decay=3   SH 1.50  TO 0.399  (R113b)  <-- attack target
  decay=5   SH 1.33  TO 0.329  (R113c)
  decay=7   SH 1.18  TO 0.288  (R113d)
  decay=10+pf20  SH 0.57  TO 0.195  (R113h, killed SH)

R113b best balance: SH +0.25 above gate, TO -0.20 from gate.
Need 50% TO reduction without losing 0.25 SH.

Other ungated options:
  R113j blend(sign+tsrank)  SH 1.34  TO 0.327  SC 0.151

Untried TO-cutters on this signal:
  1) truncation (0.05 / 0.10 / 0.15 -- tighter or looser)
  2) neutralization swap (INDUSTRY / SECTOR / MARKET / NONE)
  3) hump at micro threshold (0.005)
  4) signal-level smoothing: sign(ts_mean(returns, k)) input to LDV
  5) platform decay 15 with outer decay 3 (R113b had pf=8)
  6) longer LDV d on smoothed-sign input (d makes a difference for stable input)

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r114")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(neutralization: str = "SUBINDUSTRY", decay: int = 8,
             truncation: float = 0.08) -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": decay, "truncation": truncation,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


# Base signals
S_DECAY3 = "zscore(ts_decay_linear(zscore(last_diff_value(sign(returns), 10)), 3))"
S_DECAY4 = "zscore(ts_decay_linear(zscore(last_diff_value(sign(returns), 10)), 4))"


VARIANTS = [
    # 1) R113b + TIGHTER TRUNC 0.05
    {"label": "R114a_decay3_trunc005",
     "expression": S_DECAY3,
     "settings": settings(truncation=0.05)},

    # 2) R113b + LOOSER TRUNC 0.15
    {"label": "R114b_decay3_trunc015",
     "expression": S_DECAY3,
     "settings": settings(truncation=0.15)},

    # 3) R113b + INDUSTRY NEUT
    {"label": "R114c_decay3_neut_industry",
     "expression": S_DECAY3,
     "settings": settings(neutralization="INDUSTRY")},

    # 4) R113b + MARKET NEUT (broadest)
    {"label": "R114d_decay3_neut_market",
     "expression": S_DECAY3,
     "settings": settings(neutralization="MARKET")},

    # 5) R113b + PLATFORM DECAY=15
    {"label": "R114e_decay3_pf_decay15",
     "expression": S_DECAY3,
     "settings": settings(decay=15)},

    # 6) R113b + HUMP=0.005 (very gentle, after zscore)
    {"label": "R114f_decay3_hump_micro",
     "expression": f"zscore(hump({S_DECAY3}, hump=0.005))"},

    # 7) DECAY=4 (between 3 and 5 -- interpolation)
    {"label": "R114g_decay4",
     "expression": S_DECAY4},

    # 8) SIGNAL-LEVEL SMOOTH: sign(ts_mean(returns,3)) input -- fewer flips
    {"label": "R114h_smoothed_sign_input",
     "expression": "zscore(ts_decay_linear("
                   "zscore(last_diff_value(sign(ts_mean(returns, 3)), 20)), 3))"},

    # 9) SIGNAL-LEVEL SMOOTH bigger: sign(ts_mean(returns,5)) + d=30 LDV
    {"label": "R114i_smoothed_sign_d30",
     "expression": "zscore(ts_decay_linear("
                   "zscore(last_diff_value(sign(ts_mean(returns, 5)), 30)), 3))"},

    # 10) R113j BLEND + ts_mean(3) (cut blend TO 0.327)
    {"label": "R114j_blend_tsmean3",
     "expression": "zscore(ts_mean(ts_decay_linear(add("
                   "zscore(last_diff_value(sign(returns), 10)), "
                   "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10)))"
                   "), 5), 3))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r114_signldv_to_cutters_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R114: push R113b (sign-LDV+decay3 SH 1.50 TO 0.399) past TO gate "
        "via truncation tweaks, neutralization swaps, micro hump, "
        "signal-level sign smoothing, and platform decay.\n"
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
            log.warning(f"      FAIL: {res.get('error', '?')[:200]}")
    md = "# R114 sign-LDV TO cutters\n\n"
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
