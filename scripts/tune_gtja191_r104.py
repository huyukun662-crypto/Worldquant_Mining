"""Round 104: 10 cold/niche factors. Avoid all explored families:
  - NO MA60 close/MA60 family (R86-R101)
  - NO Parkinson ln(H/L)^2 family (R94-R96)
  - NO realized vol family
  - NO rv*acc*vol (portfolio 9q9o0zme)

Try rare operators: ts_arg_max, ts_arg_min, ts_regression,
rank-based corr, vwap-dispersion. Use diverse fields: adv5, adv20,
adv60, vwap, returns lags.

  C1   ts_arg_max(close, 60) reversed -- days since 60d high (long-stale)
  C2   ts_arg_min(close, 60) reversed -- days since 60d low (short-bounce)
  C3   ts_corr(returns, ts_delay(returns, 1), 60) reversed -- 1d autocorr
  C4   ts_mean(divide(close, vwap), 60) reversed -- close-vwap drift
  C5   ts_zscore(divide(subtract(high, low), close), 60) reversed -- range outlier
  C6   ts_regression(close, ts_step(1), 60) reversed -- 60d slope
  C7   ts_corr(adv20, returns, 60) reversed -- liquidity-return coupling
  C8   ts_corr(rank(volume), rank(returns), 60) reversed -- Spearman VR
  C9   ts_std_dev(divide(close, vwap), 60) reversed -- VWAP consistency
  C10  divide(adv5, adv60) reversed -- short-vs-long volume regime

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r104")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(neutralization: str = "SUBINDUSTRY") -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": 0.08,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 15) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


def three_tier(signal: str) -> str:
    """3-tier canonical from cheat sheet: ts_rank -> group_neutralize -> decay.
    Completely different from PV (signed_power) and linear (zscore-only) outers."""
    return f"group_neutralize(ts_rank(reverse({signal}), 60), subindustry)"


# the 10 cold cores
C1  = "ts_arg_max(close, 60)"
C2  = "ts_arg_min(close, 60)"
C3  = "ts_corr(returns, ts_delay(returns, 1), 60)"
C4  = "ts_mean(divide(close, vwap), 60)"
C5  = "ts_zscore(divide(subtract(high, low), close), 60)"
C6  = "ts_regression(close, ts_step(1), 60, 0)"  # last arg = slope return mode
C7  = "ts_corr(adv20, returns, 60)"
C8  = "ts_corr(rank(volume), rank(returns), 60)"
C9  = "ts_std_dev(divide(close, vwap), 60)"
C10 = "divide(adv5, adv60)"

# outer wrapper: zscore(ts_decay_linear(group_neutralize(ts_rank(reverse(core), 60), subindustry), 15))
VARIANTS = [
    {"label": "C1_days_since_high",      "expression": W(three_tier(C1))},
    {"label": "C2_days_since_low",       "expression": W(three_tier(C2))},
    {"label": "C3_autocorr_1d_rev",      "expression": W(three_tier(C3))},
    {"label": "C4_close_vwap_drift",     "expression": W(three_tier(C4))},
    {"label": "C5_range_zscore_rev",     "expression": W(three_tier(C5))},
    {"label": "C6_slope60_rev",          "expression": W(three_tier(C6))},
    {"label": "C7_liquidity_ret_corr",   "expression": W(three_tier(C7))},
    {"label": "C8_spearman_VR",          "expression": W(three_tier(C8))},
    {"label": "C9_vwap_dispersion",      "expression": W(three_tier(C9))},
    {"label": "C10_adv5_over_adv60",     "expression": W(three_tier(C10))},
]
for v in VARIANTS:
    v["settings"] = settings()


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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r104_10_cold_factors_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R104: 10 cold/niche factors avoiding MA60/Parkinson/RV families.\n"
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
    md = "# R104 ten cold factors\n\n"
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
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | - | no | - | "
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
