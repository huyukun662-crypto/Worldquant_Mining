"""Round 111: R110e turnover taming -- preserve SH 1.31, cut TO from 0.589.

R110 breakthrough: R110e = zscore(reverse(last_diff_value(returns, 10)))
  SH=1.31  TO=0.589  conc=PASS  sub=PASS(0.92)  SC={A1nn:-0.04, 1Yop:0.13, 9q9o:0.31}
  ALL gates pass except TO. Gate is TO<0.20.

Prior taming attempts on cold signals all destroyed SH:
  R109a tradewhen+5d decay   1.06 -> 0.90
  R109b grouprank+decay       0.95 -> 0.45
  R110i hump after rank       inf -> 0.47

This round: try EVERY turnover-cutting technique on R110e baseline.
If any preserves SH > 1.25 AND drops TO < 0.20 -> submit.

Techniques:
  1) longer LDV window (d=20, 60)            -- fewer signal updates
  2) ts_mean(signal, 5) wrap                 -- temporal averaging
  3) ts_decay_linear(signal, k) outer        -- linear smoothing
  4) hump(signal, hump=0.01-0.10)            -- micro-change suppression
  5) bucket(rank(signal))                    -- discretize
  6) trade_when regime gate                  -- frequency cutting

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r111")
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


def LDV(d):
    return f"zscore(reverse(last_diff_value(returns, {d})))"


VARIANTS = [
    # 1) LONGER LDV WINDOW: d=20 (was 10)
    {"label": "R111a_ldv_d20",
     "expression": LDV(20)},

    # 2) LONGER LDV WINDOW: d=60
    {"label": "R111b_ldv_d60",
     "expression": LDV(60)},

    # 3) TS_MEAN(5) WRAP on d=10 LDV
    {"label": "R111c_ldv_d10_tsmean5",
     "expression": f"zscore(ts_mean({LDV(10)}, 5))"},

    # 4) TS_DECAY_LINEAR(5) OUTER on d=10 LDV (minimal smoothing)
    {"label": "R111d_ldv_d10_decay5",
     "expression": f"zscore(ts_decay_linear({LDV(10)}, 5))"},

    # 5) TS_DECAY_LINEAR(15) OUTER on d=10 LDV
    {"label": "R111e_ldv_d10_decay15",
     "expression": f"zscore(ts_decay_linear({LDV(10)}, 15))"},

    # 6) HUMP gentle threshold 0.01
    {"label": "R111f_ldv_d10_hump01",
     "expression": f"zscore(hump({LDV(10)}, hump=0.01))"},

    # 7) HUMP medium threshold 0.03
    {"label": "R111g_ldv_d10_hump03",
     "expression": f"zscore(hump({LDV(10)}, hump=0.03))"},

    # 8) BUCKET-based discretization (4 buckets)
    {"label": "R111h_ldv_d10_bucket",
     "expression": f"zscore(bucket(rank({LDV(10)}), buckets=\"0.25,0.5,0.75\"))"},

    # 9) TRADE_WHEN regime gate (high-vol only) on R110e
    {"label": "R111i_tradewhen_ldv",
     "expression": f"trade_when("
                   f"greater(ts_rank(ts_std_dev(returns, 20), 60), 0.5), "
                   f"{LDV(10)}, -1)"},

    # 10) COMBO: d=20 LDV + ts_mean(5) (both TO-cutting techniques stacked)
    {"label": "R111j_ldv_d20_tsmean5",
     "expression": f"zscore(ts_mean({LDV(20)}, 5))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r111_ldv_to_taming_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R111: tame R110e (SH 1.31, TO 0.589) -- preserve SH, cut TO<0.20.\n"
        "Techniques: longer LDV window, ts_mean wrap, ts_decay_linear outer, "
        "hump (0.01/0.03), bucket discretize, trade_when regime gate, combos.\n"
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
    md = "# R111 LDV turnover taming\n\n"
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
