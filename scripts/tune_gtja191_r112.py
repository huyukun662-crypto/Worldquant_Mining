"""Round 112: smarter LDV inputs + settings-level decay tuning.

R111 critical finding: last_diff_value(returns, d) is INVARIANT in d for
daily returns (they differ every day, so LDV degenerates to ts_delay(returns, 1)).
  R110e/R111a/R111b ALL gave SH=1.31 TO=0.589 regardless of d=10/20/60.

To make LDV's d parameter meaningful, feed it a STABLE input that
doesn't change daily. Then larger d -> remember older non-current value.

Stable LDV inputs to try:
  sign(returns)              -- only changes on sign flip (few changes/wk)
  ts_mean(returns, 5)        -- smoothed return
  ts_rank(returns, 20)       -- rank changes slowly
  rank(returns)              -- cross-sectional rank

Best TO-tame finding from R111:
  R111d  decay=5 outer -> SH 1.21 TO 0.336 SC 0.281  (only 0.04 below SH gate!)

Other levers untried:
  - Lower platform decay (settings.decay=4) + outer ts_decay_linear
  - Bucket output needs no zscore (Unit[Group:1])

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r112")
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
    # 1) LDV on sign(returns) -- d should matter now
    {"label": "R112a_ldv_sign_d10",
     "expression": "zscore(reverse(last_diff_value(sign(returns), 10)))"},

    # 2) LDV on smoothed returns -- d should matter
    {"label": "R112b_ldv_tsmean5_d10",
     "expression": "zscore(reverse(last_diff_value(ts_mean(returns, 5), 10)))"},

    # 3) LDV on rolling rank
    {"label": "R112c_ldv_tsrank20_d10",
     "expression": "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10)))"},

    # 4) LDV on cross-sectional rank
    {"label": "R112d_ldv_rank_d10",
     "expression": "zscore(reverse(last_diff_value(rank(returns), 10)))"},

    # 5) R111d winner + EXTRA ts_mean wrap
    {"label": "R112e_ldv_decay5_tsmean3",
     "expression": "zscore(ts_mean(ts_decay_linear("
                   "zscore(reverse(last_diff_value(returns, 10))), 5), 3))"},

    # 6) R111d with HIGHER PLATFORM DECAY (decay=20)
    {"label": "R112f_ldv_decay5_pf_decay20",
     "expression": "zscore(ts_decay_linear("
                   "zscore(reverse(last_diff_value(returns, 10))), 5))",
     "settings": settings(decay=20)},

    # 7) R111d with PLATFORM DECAY=4 + outer decay=15
    {"label": "R112g_ldv_decay15_pf_decay4",
     "expression": "zscore(ts_decay_linear("
                   "zscore(reverse(last_diff_value(returns, 10))), 15))",
     "settings": settings(decay=4)},

    # 8) BUCKET fix: omit outer zscore (bucket returns Unit[Group:1])
    {"label": "R112h_ldv_bucket_no_zscore",
     "expression": "bucket(rank("
                   "zscore(reverse(last_diff_value(returns, 10)))"
                   "), buckets=\"0.25,0.5,0.75\")"},

    # 9) LDV on sign + decay (compound TO suppressors)
    {"label": "R112i_ldv_sign_decay10",
     "expression": "zscore(ts_decay_linear("
                   "reverse(last_diff_value(sign(returns), 10)), 10))"},

    # 10) LDV on ts_mean(5) + decay (compound)
    {"label": "R112j_ldv_tsmean5_decay10",
     "expression": "zscore(ts_decay_linear("
                   "reverse(last_diff_value(ts_mean(returns, 5), 10)), 10))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r112_smart_ldv_input_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R112: feed LDV stable inputs (sign/ts_mean/ts_rank) so d matters; "
        "also probe platform-level decay settings.\n"
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
    md = "# R112 smart LDV input + platform decay\n\n"
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
