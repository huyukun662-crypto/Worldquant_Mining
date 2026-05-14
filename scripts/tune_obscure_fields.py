"""Round 56: low-correlation alphas built on OBSCURE data fields.

Source: live data-field probe under 2841262992@qq.com (USA TOP3000
delay=1). Filter: MATRIX type, coverage>=0.85, userCount==0,
alphaCount==0 -- truly rare across 3 categories (fundamental + news +
socialmedia) to introduce orthogonal signals to our PV-heavy portfolio.

  OBS1  allocated_sbp_expense_total (fundamental, usr=0)
        ts_delta(SBC,60) -- share-based-comp dilution detector
  OBS2  common_shares_outstanding_total (fundamental, usr=0)
        -ts_delta(shares,60) -- net buyback detector (directional)
  OBS3  mean_event_novelty_score (news, usr=0, cov=1.00)
        spike -> short-horizon drift signal
  OBS4  mean_news_impact_projection (news, usr=0, cov=1.00)
        projected market impact of recent news flashes
  OBS5  snt_social_volume_fast_d1 (socialmedia, usr=0, cov=1.00)
        normalized tweet volume x returns interaction

All activated with reverse(ts_zscore(returns,5)) * volwt to lift SH; the
slow-moving rare field tilts the universe, the PV kernel times entries.
trunc=0.08 + SUBINDUSTRY to absorb expected industry concentration.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r56")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

BASE = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 8, "truncation": 0.08, "neutralization": "SUBINDUSTRY",
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF",
    "testPeriod": "P0Y0M",
}

# 5-day reversal (multiply by -1 via 'reverse' wrapper around ts_zscore)
REV = "reverse(ts_zscore(returns, 5))"
VOLWT = "log(add(divide(volume, adv20), 1))"


def _activate(signal_expr: str) -> str:
    """Wrap a slow-moving signal with PV-reversal activation + decay."""
    return (
        f"zscore(ts_decay_linear(multiply(multiply("
        f"rank({signal_expr}), {REV}), {VOLWT}), 25))"
    )


VARIANTS = [
    # rising SBC = dilution = bearish; reverse(ts_delta) -> long shrinking SBC
    {"label": "OBS1_sbp_decline",
     "field": "allocated_sbp_expense_total",
     "rationale": "SBC dilution detector (fundamental, usr=0)",
     "signal": "subtract(ts_delay(allocated_sbp_expense_total, 60), allocated_sbp_expense_total)"},
    # shrinking shares outstanding = buyback = bullish
    {"label": "OBS2_buyback",
     "field": "common_shares_outstanding_total",
     "rationale": "net buyback detector (fundamental, usr=0)",
     "signal": "subtract(ts_delay(common_shares_outstanding_total, 60), common_shares_outstanding_total)"},
    # news event novelty spike -> drift
    {"label": "OBS3_news_novelty",
     "field": "mean_event_novelty_score",
     "rationale": "news event novelty (news, usr=0, cov=1.0)",
     "signal": "mean_event_novelty_score"},
    # projected impact -> tilt
    {"label": "OBS4_news_impact",
     "field": "mean_news_impact_projection",
     "rationale": "projected news impact (news, usr=0, cov=1.0)",
     "signal": "mean_news_impact_projection"},
    # social-media buzz volume -> drift
    {"label": "OBS5_social_vol",
     "field": "snt_social_volume_fast_d1",
     "rationale": "normalized tweet volume (socialmedia, usr=0, cov=1.0)",
     "signal": "snt_social_volume_fast_d1"},
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    r5 = _load(REPO / "scripts" / "run_5agent_workflow.py", "r5")
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r56_obscure_fields_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "5 alphas built on ultra-rare data fields (usr<=1) to reduce "
        "correlation with prior PV-only portfolio.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        expression = _activate(v["signal"])
        log.info(f"  [{i}/5] {v['label']}: {v['rationale']}")
        log.info(f"      field: {v['field']}")
        log.info(f"      expr: {expression}")
        try:
            res = r5.submit(cm.session, expression, BASE)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "field": v["field"],
                 "rationale": v["rationale"], "expression": expression, **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT",
                                        "LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} "
                             f"value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:140]}")
    md = "# R56 obscure-field alphas (low-correlation portfolio diversifier)\n\n"
    md += ("| variant | field | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---|---:|---:|---:|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        conc_ok = conc.get('result') == 'PASS'
        sub_ok = sub.get('result') == 'PASS'
        all_pass = (r['sharpe'] >= 1.75 and r['turnover'] < 0.20
                    and r['fitness'] > 1.25 and conc_ok and sub_ok)
        if all_pass:
            survivors.append(r)
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['field']} | {r['sharpe']:+.3f} | "
                f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += f"| {r['variant']} | {r['field']} | FAIL | - | - | - | - | no |\n"
    md += f"\n**Survivors: {len(survivors)}/{len(results)}**\n"
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
