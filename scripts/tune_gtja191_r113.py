"""Round 113: unreverse sign-LDV + push ts_rank-LDV (R112c) past TO gate.

R112 produced TWO breakthrough leads:

  LEAD A: R112a sign-LDV inverted
    expr:  zscore(reverse(last_diff_value(sign(returns), 10)))
    SH -1.72 TO 0.603 conc=PASS sub=FAIL(-1.58) SC max 0.20
    UNREVERSED: SH +1.72 TO 0.603 conc=PASS sub=PASS(+1.58) SC max 0.20
    -> If TO can drop to <0.20, this is SH 1.72 alpha (highest cold ever).
    TO still 3x over gate. But R112i (sign-LDV+decay10) gave inverted
    SH -1.08 TO 0.239 -- meaning unreversed SH +1.08 TO 0.239 sub PASS.
    -> Outer decay reduces both SH and TO. Sweep decay 0/3/5/7.

  LEAD B: R112c ts_rank-LDV
    expr:  zscore(reverse(last_diff_value(ts_rank(returns, 20), 10)))
    SH +1.43 TO 0.623 SC 0.149 conc+sub PASS
    -> Highest cold SH + lowest cold SC, but TO 0.623 way over.
    R112g (platform decay=4 + outer decay=15) cut TO to 0.268 but SH 1.20.
    -> Try aggressive platform decay + ts_rank window sweep.

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r113")
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
    # 1) LEAD A: SIGN-LDV UNREVERSED, bare (expect SH +1.72 TO 0.60)
    {"label": "R113a_sign_ldv_pos_bare",
     "expression": "zscore(last_diff_value(sign(returns), 10))"},

    # 2) LEAD A: SIGN-LDV UNREVERSED + decay=3 outer (mild smoothing)
    {"label": "R113b_sign_ldv_pos_decay3",
     "expression": "zscore(ts_decay_linear("
                   "zscore(last_diff_value(sign(returns), 10)), 3))"},

    # 3) LEAD A: SIGN-LDV UNREVERSED + decay=5
    {"label": "R113c_sign_ldv_pos_decay5",
     "expression": "zscore(ts_decay_linear("
                   "zscore(last_diff_value(sign(returns), 10)), 5))"},

    # 4) LEAD A: SIGN-LDV UNREVERSED + decay=7
    {"label": "R113d_sign_ldv_pos_decay7",
     "expression": "zscore(ts_decay_linear("
                   "zscore(last_diff_value(sign(returns), 10)), 7))"},

    # 5) LEAD B: R112c + PLATFORM DECAY=30 (push TO down hard)
    {"label": "R113e_tsrank_ldv_pf_decay30",
     "expression": "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10)))",
     "settings": settings(decay=30)},

    # 6) LEAD B: R112c + OUTER ts_decay_linear(15)
    {"label": "R113f_tsrank_ldv_decay15",
     "expression": "zscore(ts_decay_linear("
                   "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10))), 15))"},

    # 7) LEAD B: WIDER WINDOWS -- ts_rank(60) + LDV(d=30)
    {"label": "R113g_tsrank60_ldv_d30",
     "expression": "zscore(reverse(last_diff_value(ts_rank(returns, 60), 30)))"},

    # 8) LEAD B: COMPOUND -- R112c + outer decay 10 + platform decay 20
    {"label": "R113h_tsrank_decay10_pf_decay20",
     "expression": "zscore(ts_decay_linear("
                   "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10))), 10))",
     "settings": settings(decay=20)},

    # 9) LEAD B alt: ts_rank(5) faster + LDV(d=5) faster
    {"label": "R113i_tsrank5_ldv_d5",
     "expression": "zscore(reverse(last_diff_value(ts_rank(returns, 5), 5)))"},

    # 10) BLEND: sign-LDV pos + ts_rank-LDV (two orthogonal cold leads stacked)
    {"label": "R113j_blend_sign_tsrank",
     "expression": "zscore(ts_decay_linear(add("
                   "zscore(last_diff_value(sign(returns), 10)), "
                   "zscore(reverse(last_diff_value(ts_rank(returns, 20), 10)))"
                   "), 5))"},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r113_unrev_and_tsrank_push_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R113: unreverse sign-LDV (R112a SH -1.72 -> +1.72?) and push "
        "ts_rank-LDV (R112c SH 1.43 TO 0.62) TO down via platform decay, "
        "outer decay, wider/narrower windows, and blends.\n"
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
    md = "# R113 unreverse + tsrank push\n\n"
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
