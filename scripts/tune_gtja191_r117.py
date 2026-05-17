"""Round 117: BREAK GATE -- R116j blend at 0.02 SH below + sub-FAIL fix.

R116 BREAKTHROUGH lead R116j (MA5-cross + buyback blend, decay=3):
  SH +1.23 TO 0.196 SC 0.491 conc=PASS sub=FAIL(0.52)
  -- TO PASSES gate (<0.20)!! Need SH +0.02 and sub-SH fix.

Other R116 findings:
  R116a MA3-cross bare:  SH 1.48 TO 0.516 SC 0.20 conc+sub PASS
    -- MA3 is a STRONGER BASE than MA5 (1.48 vs 1.35).
    -- Sub-SH passes (in checks). Use as new base for blend.
  R116b MA7-cross:       SH 1.12
  R116c MA10-cross:      SH 0.97
  R116h/i MA5 d=20/30:   identical to d=10  -- LDV d still invariant on MA-cross input.
  R116d MA5 decay=3:     SH 1.16 TO 0.332 (decay drops SH and TO mildly)
  R116g pf decay=20:     SH 0.98 TO 0.269

R117 plan: build on R116j with MA3 base + sub-fix tweaks.

  MA3 + buyback blends:
    R117a MA3 + buyback decay=3      (was MA5; should give higher SH)
    R117b MA3 + buyback decay=5      (more smoothing)
    R117c MA3 + buyback decay=7
    R117d MA3 + buyback weighted 2:1 (MA3 heavier)
    R117e MA3 + buyback weighted 1:2 (buyback heavier, lower TO)

  R116j fix variants (sub-FAIL):
    R117f R116j + INDUSTRY neut       (less aggressive neut keeps cross-sec)
    R117g R116j + MARKET neut
    R117h R116j + truncation=0.05    (tighter weights)
    R117i R116j + decay=5            (try a hair more smoothing -- might pass)

  Triple blend (MA3 + tsrank + buyback):
    R117j MA3 + tsrank-LDV + buyback

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r117")
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


# Components
def MA_CROSS_LDV(ma, d):
    return ("zscore(last_diff_value("
            f"sign(subtract(close, ts_mean(close, {ma}))), {d}))")

MA3 = MA_CROSS_LDV(3, 10)
MA5 = MA_CROSS_LDV(5, 10)
BUYBACK = "zscore(reverse(divide(subtract(sharesout, ts_delay(sharesout, 252)), sharesout)))"
TSRANK = "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10)))"

# R116j baseline reference
R116J = f"zscore(ts_decay_linear(add({MA5}, {BUYBACK}), 3))"


VARIANTS = [
    # MA3 + buyback blend, decay sweep
    {"label": "R117a_ma3_buyback_d3",
     "expression": f"zscore(ts_decay_linear(add({MA3}, {BUYBACK}), 3))"},
    {"label": "R117b_ma3_buyback_d5",
     "expression": f"zscore(ts_decay_linear(add({MA3}, {BUYBACK}), 5))"},
    {"label": "R117c_ma3_buyback_d7",
     "expression": f"zscore(ts_decay_linear(add({MA3}, {BUYBACK}), 7))"},

    # MA3 + buyback weighted
    {"label": "R117d_ma3x2_buyback",
     "expression": f"zscore(ts_decay_linear("
                   f"add(multiply({MA3}, 2), {BUYBACK}), 3))"},
    {"label": "R117e_ma3_buybackx2",
     "expression": f"zscore(ts_decay_linear("
                   f"add({MA3}, multiply({BUYBACK}, 2)), 3))"},

    # R116j fix variants (target sub-FAIL)
    {"label": "R117f_r116j_INDUSTRY",
     "expression": R116J,
     "settings": settings(neutralization="INDUSTRY")},
    {"label": "R117g_r116j_MARKET",
     "expression": R116J,
     "settings": settings(neutralization="MARKET")},
    {"label": "R117h_r116j_trunc05",
     "expression": R116J,
     "settings": settings(truncation=0.05)},
    {"label": "R117i_r116j_decay5",
     "expression": f"zscore(ts_decay_linear(add({MA5}, {BUYBACK}), 5))"},

    # Triple blend with all 3 cold leads
    {"label": "R117j_triple_ma3_tsrank_buyback",
     "expression": f"zscore(ts_decay_linear("
                   f"add(add({MA3}, {TSRANK}), {BUYBACK}), 3))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r117_break_gate_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R117: break gate via MA3 (stronger base) + buyback blend; "
        "and fix R116j sub-FAIL via neut/trunc/decay tweaks.\n"
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
    md = "# R117 break gate\n\n"
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
