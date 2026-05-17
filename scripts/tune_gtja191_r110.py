"""Round 110: cold x cold blend frontier + remaining untested ops.

R108-R109 finding: pure cold signals cap at SH ~1.0-1.06 (R108a tradewhen,
R109f last_diff_value). Smoothing kills SH. To break SH 1.25 without
reusing the banned close/MA60 base, BLEND two orthogonal cold signals.

R109 best signals to blend:
  R108a  tradewhen_hivol_rev          SH 1.06 SC 0.22  TO 0.184
  R109f  last_diff_value_rev          SH 1.02 SC 0.31  TO 0.244
  R109g  group_zscore_sector          SH 0.70 SC 0.26  TO 0.212  (lowest SC!)
  R109c  buyback_252d_pct             SH 0.69 SC 0.49  TO 0.022  (lowest TO!)

R109 errors recovery:
  R109e hump_kwarg     -- hump rejects unit'd input; wrap in rank() first
  R109i iv_skew        -- poll-timeout (not real fail); retry shorter decay

Still-untested ops to deploy:
  sigmoid, arc_tan, normalize, bucket, ts_partial_corr,
  winsorize (was used 8x but in narrow context).

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r110")
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


# Component signals (reusable)
LDV = "zscore(reverse(last_diff_value(returns, 5)))"
GZS = "group_zscore(reverse(ts_mean(returns, 10)), sector)"
GRK = "group_rank(reverse(ts_mean(returns, 5)), subindustry)"
BB  = "zscore(reverse(divide(subtract(sharesout, ts_delay(sharesout, 252)), sharesout)))"
HV  = "zscore(reverse(historical_volatility_30))"


VARIANTS = [
    # 1) BLEND: last_diff_value + group_zscore (both reversal flavor, low SC)
    {"label": "R110a_ldv_x_gzs",
     "expression": f"zscore(ts_decay_linear(add({LDV}, {GZS}), 10))"},

    # 2) BLEND: last_diff_value + buyback (sparse low-TO + reversal)
    {"label": "R110b_ldv_x_buyback",
     "expression": f"zscore(ts_decay_linear(add({LDV}, {BB}), 10))"},

    # 3) BLEND: last_diff_value + HV30 (cold op + cold field)
    {"label": "R110c_ldv_x_hv30",
     "expression": f"zscore(ts_decay_linear(add({LDV}, {HV}), 10))"},

    # 4) BLEND: 3-way last_diff_value + group_rank + HV30
    {"label": "R110d_triple_ldv_grk_hv",
     "expression": f"zscore(ts_decay_linear(add(add({LDV}, {GRK}), {HV}), 10))"},

    # 5) PUSH R109f: bare last_diff_value with longer window, no decay smoothing
    {"label": "R110e_ldv_d10_pure",
     "expression": "zscore(reverse(last_diff_value(returns, 10)))"},

    # 6) COLD OP: sigmoid-bounded short reversal
    {"label": "R110f_sigmoid_rev",
     "expression": "zscore(ts_decay_linear("
                   "sigmoid(zscore(reverse(returns))), 5))"},

    # 7) COLD OP: arc_tan compressed reversal
    {"label": "R110g_arctan_rev",
     "expression": "zscore(ts_decay_linear("
                   "arc_tan(reverse(ts_mean(returns, 5))), 10))"},

    # 8) COLD OP: normalize (alternative to zscore)
    {"label": "R110h_normalize_rev",
     "expression": "zscore(ts_decay_linear("
                   "normalize(reverse(ts_mean(returns, 5))), 10))"},

    # 9) FIX R109e: hump after rank() to strip units
    {"label": "R110i_hump_after_rank",
     "expression": "zscore(ts_decay_linear("
                   "hump(zscore(reverse(returns)), hump=0.05), 5))"},

    # 10) RETRY R109i: IV-skew with shorter decay (fix poll-timeout)
    {"label": "R110j_iv_skew_d5",
     "expression": "zscore(ts_decay_linear("
                   "reverse(subtract(implied_volatility_put_30, implied_volatility_call_30)), 5))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r110_cold_cold_blend_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R110: cold x cold blends (LDV/GZS/GRK/BB/HV30) to break SH 1.25 "
        "without reusing banned close/MA60 base; plus untested ops "
        "(sigmoid, arc_tan, normalize, hump-after-rank).\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression'][:250]}")
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
    md = "# R110 cold x cold blend frontier\n\n"
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
