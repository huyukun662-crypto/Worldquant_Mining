"""Round 109: R108 follow-up -- salvage 3 low-SC leads + new cold ops/fields.

R108 yielded 0/10 gate-pass but 3 low-SC leads:
  R108a tradewhen_hivol_rev  SH 1.06 SC 0.22  (need SH +0.20)
  R108e grouprank_subind_mom SH 0.95 SC 0.14  (TO 0.31 too high, need smoothing)
  R108g buyback_sharesout    SH 0.44 TO 0.045 (need SH boost via longer window)

R108 errors to fix:
  R108d hump:        "Invalid number of inputs : 2"  -> use hump=0.05 KWARG
  R108f size(cap):   "Incompatible unit for log"     -> rank(cap) strips units
  R108i analyst:     "Invalid data field"            -> retry (transient?)
  R108j jump_decay:  "inaccessible operator"         -> skip, use ts_mean smoothing

Cold ops still untested: last_diff_value, group_zscore, normalize, scale.
Cold fields still untested: dividend, implied_volatility_put_30.

10 variants:
  R109a tradewhen_smooth          -- salvage R108a: 5d smoothed inner signal
  R109b grouprank_decay           -- salvage R108e: wrap in ts_decay_linear
  R109c buyback_252d_pct          -- salvage R108g: 252d % change in sharesout
  R109d size_rank                 -- fix R108f: reverse(rank(cap))
  R109e hump_kwarg                -- fix R108d: hump(x, hump=0.05)
  R109f last_diff_value_rev       -- COLD op: last_diff_value(returns, 5)
  R109g group_zscore_sector       -- COLD op + group: group_zscore + sector
  R109h div_yield                 -- COLD field: dividend / close
  R109i iv_skew                   -- COLD field pair: put30 - call30
  R109j hv30_solo                 -- COLD field bare: reverse(HV30)
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r109")
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
    # 1) SALVAGE R108a: trade_when w/ 5d smoothed inner signal (was bare reverse(returns))
    {"label": "R109a_tradewhen_smooth",
     "expression": "trade_when("
                   "greater(ts_rank(ts_std_dev(returns, 20), 60), 0.7), "
                   "zscore(ts_decay_linear(reverse(returns), 5)), -1)"},

    # 2) SALVAGE R108e: group_rank inside ts_decay_linear to cut TO from 0.31
    {"label": "R109b_grouprank_decay",
     "expression": "zscore(ts_decay_linear("
                   "group_rank(reverse(ts_mean(returns, 5)), subindustry), 15))"},

    # 3) SALVAGE R108g: 252d % change in sharesout (was 60d absolute diff)
    {"label": "R109c_buyback_252d_pct",
     "expression": "zscore(ts_decay_linear("
                   "reverse(divide(subtract(sharesout, ts_delay(sharesout, 252)), sharesout)), 20))"},

    # 4) FIX R108f: rank() strips units, then reverse for small-cap effect
    {"label": "R109d_size_rank",
     "expression": "zscore(ts_decay_linear(reverse(rank(cap)), 20))"},

    # 5) FIX R108d: hump uses kwarg form (not positional)
    {"label": "R109e_hump_kwarg",
     "expression": "zscore(ts_decay_linear("
                   "hump(reverse(returns), hump=0.05), 5))"},

    # 6) COLD OP: last_diff_value -- returns the last value not equal to current
    {"label": "R109f_last_diff_value_rev",
     "expression": "zscore(ts_decay_linear("
                   "reverse(last_diff_value(returns, 5)), 10))"},

    # 7) COLD OP + GROUP: group_zscore within sector (was subindustry+rank)
    {"label": "R109g_group_zscore_sector",
     "expression": "group_zscore(reverse(ts_mean(returns, 10)), sector)"},

    # 8) COLD FIELD: dividend yield
    {"label": "R109h_div_yield",
     "expression": "zscore(ts_decay_linear(divide(dividend, close), 30))"},

    # 9) COLD FIELD PAIR: IV skew = put - call (positive = fear/skew)
    {"label": "R109i_iv_skew",
     "expression": "zscore(ts_decay_linear("
                   "reverse(subtract(implied_volatility_put_30, implied_volatility_call_30)), 15))"},

    # 10) COLD FIELD SOLO: HV30 reversal alone (not the spread)
    {"label": "R109j_hv30_solo",
     "expression": "zscore(ts_decay_linear(reverse(historical_volatility_30), 15))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r109_cold_followup_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R109: salvage R108 low-SC leads (tradewhen, grouprank, buyback) + "
        "fix R108 errors (hump kwarg, rank(cap)) + new cold ops "
        "(last_diff_value, group_zscore) + new cold fields (dividend, IV-put, HV30 solo).\n"
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
    md = "# R109 cold followup\n\n"
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
