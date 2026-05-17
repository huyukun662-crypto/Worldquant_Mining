"""Round 108: 100% cold operator x cold field exploration.

Mandate: NO operator/field already heavily used across R85-R107.

Used (banned for core signal):
  ops:    signed_power, zscore(reverse(...)) on close/MA60,
          ts_mean(power(log(high/low),2),60) (parkinson family),
          ts_std_dev(close/vwap, 60) (vwap_dispersion / C9)
  fields: close+MA60 mean-rev, parkinson/RS/YZ/range vol, vwap_dispersion

Cold ops to deploy:
  trade_when, greater, days_from_last_change, sign, ts_quantile,
  hump, group_rank, jump_decay, last_diff_value

Cold fields to deploy:
  cap, sharesout, dividend
  historical_volatility_30, implied_volatility_call_30, implied_volatility_put_30
  snt1_d1_earningsrevision, snt1_d1_buyrecpercent, snt1_cored1_score

Outer shaping (ts_decay_linear + zscore) IS reused -- they are proven
shapers, not signal sources. The CORE inside is 100% new.

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7 vs portfolio
      (A1nnxAdw, 9q9o0zme, 1YopvX8W).
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r108")
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


VARIANTS = [
    # 1) CONDITIONAL alpha: short-term reversal triggered only in high-vol regime.
    {"label": "R108a_tradewhen_hivol_rev",
     "expression": "trade_when("
                   "greater(ts_rank(ts_std_dev(returns, 20), 60), 0.7), "
                   "zscore(reverse(returns)), -1)"},

    # 2) PERSISTENCE: longer runs of same-sign returns get faded.
    {"label": "R108b_persistence_fade",
     "expression": "zscore(ts_decay_linear("
                   "reverse(days_from_last_change(sign(returns))), 10))"},

    # 3) GAUSSIAN-MAPPED RANK on vol: low-vol anomaly via ts_quantile.
    {"label": "R108c_quantile_lowvol",
     "expression": "zscore(ts_decay_linear("
                   "reverse(ts_quantile(ts_std_dev(returns, 20), 252, driver=\"gaussian\")), 15))"},

    # 4) HUMP-DAMPED reversal: kills micro changes (low TO).
    {"label": "R108d_hump_reversal",
     "expression": "zscore(ts_decay_linear("
                   "hump(reverse(returns), 0.05), 5))"},

    # 5) GROUP_RANK relative momentum within subindustry (pure relative).
    {"label": "R108e_grouprank_subind_mom",
     "expression": "group_rank(reverse(ts_mean(returns, 5)), subindustry)"},

    # 6) SIZE FACTOR: small-cap effect (long small, short large).
    {"label": "R108f_size_smallcap",
     "expression": "zscore(ts_decay_linear(reverse(log(cap)), 20))"},

    # 7) BUYBACK SIGNAL: companies reducing share count outperform.
    {"label": "R108g_buyback_sharesout",
     "expression": "zscore(ts_decay_linear("
                   "reverse(subtract(sharesout, ts_delay(sharesout, 60))), 15))"},

    # 8) VOL RISK PREMIUM: IV - HV spread (option market vol premium).
    {"label": "R108h_volrisk_premium",
     "expression": "zscore(ts_decay_linear("
                   "reverse(subtract(implied_volatility_call_30, historical_volatility_30)), 15))"},

    # 9) ANALYST SENTIMENT: positive earnings revisions predict outperformance.
    {"label": "R108i_analyst_earnrev",
     "expression": "zscore(ts_decay_linear(snt1_d1_earningsrevision, 20))"},

    # 10) JUMP-DECAYED HV: jump_decay smooths sudden vol changes on HV30.
    {"label": "R108j_jumpdecay_hv30",
     "expression": "zscore(ts_decay_linear("
                   "reverse(jump_decay(historical_volatility_30, 20)), 10))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r108_cold_ops_fields_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R108: 100% cold operator x cold field exploration. "
        "Banned: signed_power(zscore(reverse(close/MA60))) + Parkinson/RS/YZ/range "
        "vol + vwap_dispersion. Try trade_when, ts_quantile, hump, group_rank, "
        "jump_decay, days_from_last_change on cap/sharesout/dividend/HV/IV/snt fields.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression'][:200]}")
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
    md = "# R108 cold ops x cold fields\n\n"
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
