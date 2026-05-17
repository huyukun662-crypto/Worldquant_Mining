"""Round 116: lock onto R115a (MA5 crossover sign-LDV) + TO taming sweep.

R115 partial finding (process died at 3/10):

  R115a  MA5 crossover sign-LDV
    expr: zscore(last_diff_value(sign(subtract(close, ts_mean(close, 5))), 10))
    SH +1.35  TO 0.420  SC 0.197  conc+sub PASS
    -- SH passes gate. TO 0.42, need <0.20.
    -- MA5-cross gives natively lower TO than sign(returns) (0.42 vs 0.60).
  R115b  MA20-cross d=30  SH 0.61 TO 0.227  -- MA20 too slow
  R115c  cumret rank      SH 0.68 sub FAIL

R116 plan: 10 candidates centered on R115a:
  Window sweep on MA period:
    R116a MA3-cross   (between sign(returns) and MA5)
    R116b MA7-cross
    R116c MA10-cross  (between MA5 and MA20)
  Decay sweep on R115a:
    R116d decay=3
    R116e decay=5
    R116f decay=7
  Platform decay:
    R116g R115a + platform decay=20
  LDV d sweep (MA5 stable enough that d matters):
    R116h R115a with d=20
    R116i R115a with d=30
  Cold blend (low-TO partner):
    R116j R115a + buyback (TO 0.022)

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r116")
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


def MA_CROSS_LDV(ma_period, ldv_d):
    return ("zscore(last_diff_value("
            f"sign(subtract(close, ts_mean(close, {ma_period}))), {ldv_d}))")


# R115a baseline reference
R115A = MA_CROSS_LDV(5, 10)

BUYBACK = "zscore(reverse(divide(subtract(sharesout, ts_delay(sharesout, 252)), sharesout)))"


VARIANTS = [
    # MA period sweep (faster -> slower) with d=10 LDV
    {"label": "R116a_ma3_cross_d10",     "expression": MA_CROSS_LDV(3, 10)},
    {"label": "R116b_ma7_cross_d10",     "expression": MA_CROSS_LDV(7, 10)},
    {"label": "R116c_ma10_cross_d10",    "expression": MA_CROSS_LDV(10, 10)},

    # Decay sweep on R115a (mild smoothing)
    {"label": "R116d_ma5_cross_decay3",
     "expression": f"zscore(ts_decay_linear({R115A}, 3))"},
    {"label": "R116e_ma5_cross_decay5",
     "expression": f"zscore(ts_decay_linear({R115A}, 5))"},
    {"label": "R116f_ma5_cross_decay7",
     "expression": f"zscore(ts_decay_linear({R115A}, 7))"},

    # Platform decay
    {"label": "R116g_ma5_cross_pf_decay20",
     "expression": R115A,
     "settings": settings(decay=20)},

    # LDV d sweep (d matters with stable MA-cross input)
    {"label": "R116h_ma5_cross_d20",     "expression": MA_CROSS_LDV(5, 20)},
    {"label": "R116i_ma5_cross_d30",     "expression": MA_CROSS_LDV(5, 30)},

    # Cold blend: MA5-cross + buyback (low-TO partner)
    {"label": "R116j_blend_ma5cross_buyback",
     "expression": f"zscore(ts_decay_linear(add({R115A}, {BUYBACK}), 3))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r116_ma5cross_taming_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R116: lock onto R115a MA5-cross sign-LDV (SH 1.35 TO 0.42) and "
        "sweep MA period, decay, platform decay, LDV d, plus cold blend.\n"
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
    md = "# R116 MA5-cross taming\n\n"
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
