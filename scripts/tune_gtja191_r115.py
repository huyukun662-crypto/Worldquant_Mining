"""Round 115: change signal SOURCE for lower native TO + cold-cold blends.

R114 confirmed sign-LDV TO floor is intrinsic. Frontier (no truncation/neut help):
  decay 0  SH 1.72 TO 0.603
  decay 3  SH 1.50 TO 0.399
  decay 5  SH 1.33 TO 0.329
  decay 7  SH 1.18 TO 0.288
  decay 9  SH 1.03 TO 0.20 (extrapolated -- below gate)

Two new directions for R115:

PATH A: Change LDV INPUT to a natively slower signal.
  sign(returns)     -- flips ~daily (TO 0.60 native)
  sign(close-MA5)   -- flips on MA cross (multi-day stable)
  sign(close-MA20)  -- even more stable
  ts_rank(ts_sum(returns,5), 20) -- cum-return rank (stable)
  ts_rank(ts_mean(returns,5), 20)

PATH B: BLEND sign-LDV (high SH, high TO) with low-TO partner.
  + R109c buyback           TO 0.022 SH 0.69
  + R112c tsrank-LDV        TO 0.623 SH 1.43  (high TO too)
  + R110h normalize_rev     TO 0.21  SH 0.82

UNTRIED: ts_partial_corr (cold op).

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r115")
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
SIGN_LDV  = "zscore(last_diff_value(sign(returns), 10))"
TSRANK_LDV = "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10)))"
BUYBACK   = "zscore(reverse(divide(subtract(sharesout, ts_delay(sharesout, 252)), sharesout)))"
NORMALIZE = "zscore(normalize(reverse(ts_mean(returns, 5))))"


VARIANTS = [
    # PATH A: change SOURCE to natively-slower signals
    # 1) MA5 crossover sign-LDV (close above/below 5d MA)
    {"label": "R115a_ma5cross_ldv",
     "expression": "zscore(last_diff_value("
                   "sign(subtract(close, ts_mean(close, 5))), 10))"},

    # 2) MA20 crossover sign-LDV (longer)
    {"label": "R115b_ma20cross_ldv",
     "expression": "zscore(last_diff_value("
                   "sign(subtract(close, ts_mean(close, 20))), 30))"},

    # 3) Cumulative-return rank LDV (smoothed via ts_sum)
    {"label": "R115c_cumret_rank_ldv",
     "expression": "zscore(reverse(last_diff_value("
                   "ts_rank(ts_sum(returns, 5), 20), 10)))"},

    # 4) ts_mean(returns,5) rank LDV
    {"label": "R115d_tsmean5_rank_ldv",
     "expression": "zscore(reverse(last_diff_value("
                   "ts_rank(ts_mean(returns, 5), 20), 10)))"},

    # 5) Long-horizon sign-LDV: sign(ts_mean(returns,10)) + d=20
    {"label": "R115e_sign_tsmean10_ldv",
     "expression": "zscore(last_diff_value("
                   "sign(ts_mean(returns, 10)), 20))"},

    # PATH B: blends with low-TO partners
    # 6) Sign-LDV decay3 + buyback (low-TO partner)
    {"label": "R115f_blend_sign_buyback",
     "expression": f"zscore(ts_decay_linear(add({SIGN_LDV}, {BUYBACK}), 3))"},

    # 7) Sign-LDV + ts_rank-LDV (both high-SH cold) -- blend with decay
    {"label": "R115g_blend_sign_tsrank_d5",
     "expression": f"zscore(ts_decay_linear(add({SIGN_LDV}, {TSRANK_LDV}), 5))"},

    # 8) Sign-LDV + normalize -- low-TO normalize partner
    {"label": "R115h_blend_sign_normalize",
     "expression": f"zscore(ts_decay_linear(add({SIGN_LDV}, {NORMALIZE}), 5))"},

    # 9) Triple blend: sign + tsrank + buyback
    {"label": "R115i_triple_sign_tsrank_buyback",
     "expression": f"zscore(ts_decay_linear(add(add({SIGN_LDV}, {TSRANK_LDV}), {BUYBACK}), 5))"},

    # 10) ts_partial_corr (COLD OP, untried)
    # ts_partial_corr(x, y, z, d) -- partial corr of x and y after controlling for z over d
    {"label": "R115j_ts_partial_corr",
     "expression": "zscore(ts_decay_linear("
                   "reverse(ts_partial_corr(returns, ts_delay(returns, 1), volume, 60)), 10))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r115_new_source_and_blends_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R115: change LDV INPUT for natively-slower signals (MA crossover, "
        "smoothed sign, cumret rank) and blend sign-LDV with low-TO partners "
        "(buyback, normalize, ts_rank-LDV).\n"
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
    md = "# R115 new source + blends\n\n"
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
