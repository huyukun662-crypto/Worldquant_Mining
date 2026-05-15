"""Round 83: try rolling Sharpe of VWAP + ts_rank-bounded + new amps.

After R77-R82 in the no-close/open space:
  ceiling for conc-PASS variants: SH ~1.00 (R80f, R81b)
  ceiling for SH>=1.5 attempts:    always conc FAIL

R83 explores fundamentally different base shapes:

  R83a  Rolling Sharpe of VWAP returns 20d  (mean/std composite)
  R83b  Rolling SH + PV6 amp
  R83c  ts_rank(VWAP, 60) reversed + PV6   (bounded-input alt)
  R83d  ts_rank(VWAPmom20, 60) rev + PV6
  R83e  Relative-vol x VWAPmom composite
  R83f  Volume-spike detector + PV6
  R83g  VWAPmom60 + PV6                     longer window
  R83h  Rolling SH + cube (zscore-IN)

Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7.
DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r83")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(truncation: float = 0.08,
             neutralization: str = "SUBINDUSTRY") -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": truncation,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


VWAP_RET1 = "divide(subtract(vwap, ts_delay(vwap, 1)), ts_delay(vwap, 1))"
VWAP_RET20 = "divide(subtract(vwap, ts_delay(vwap, 20)), ts_delay(vwap, 20))"
VWAP_RET60 = "divide(subtract(vwap, ts_delay(vwap, 60)), ts_delay(vwap, 60))"

# Rolling Sharpe of VWAP daily returns
RSH = f"divide(ts_mean({VWAP_RET1}, 20), ts_std_dev({VWAP_RET1}, 20))"
# Volume spike detector
VSPIKE = "divide(volume, ts_decay_linear(volume, 60))"
RELVOL = "divide(volume, ts_mean(volume, 60))"

R83a = W(f"reverse({RSH})")
R83b = W(f"signed_power(zscore(reverse({RSH})), 2)")  # rolling SH rev + PV6
R83c = W(f"signed_power(zscore(reverse(ts_rank(vwap, 60))), 2)")
R83d = W(f"signed_power(zscore(reverse(ts_rank({VWAP_RET20}, 60))), 2)")
R83e = W(f"signed_power(zscore(multiply({RELVOL}, reverse({VWAP_RET20}))), 2)")
R83f = W(f"signed_power(zscore({VSPIKE}), 2)")
R83g = W(f"signed_power(zscore(reverse({VWAP_RET60})), 2)")
R83h = W(f"signed_power(zscore(reverse({RSH})), 3)")  # cube


VARIANTS = [
    {"label": "R83a_rollSH_VWAP_rev",    "expression": R83a, "settings": settings()},
    {"label": "R83b_rollSH_PV6",         "expression": R83b, "settings": settings()},
    {"label": "R83c_tsrank_vwap60_PV6",  "expression": R83c, "settings": settings()},
    {"label": "R83d_tsrank_VWAPmom_PV6", "expression": R83d, "settings": settings()},
    {"label": "R83e_relvol_x_VWAPmom",   "expression": R83e, "settings": settings()},
    {"label": "R83f_vol_spike_PV6",      "expression": R83f, "settings": settings()},
    {"label": "R83g_VWAPmom60_PV6",      "expression": R83g, "settings": settings()},
    {"label": "R83h_rollSH_cube",        "expression": R83h, "settings": settings()},
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    r5 = _load(REPO / "scripts" / "run_5agent_workflow.py", "r5")
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r83_rolling_sharpe_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R83: rolling SH of VWAP + ts_rank-bounded + new no-close/open angles.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], v["settings"])
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"],
                 "settings": v["settings"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f} checks={res['checks_passed']}/{res['checks_total']}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT","LOW_SUB_UNIVERSE_SHARPE","SELF_CORRELATION"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")
    md = "# R83 rolling Sharpe + new angles\n\n"
    md += ("| variant | SH | TO | FIT | checks | conc | sub | sc | gate |\n"
           "|---|---:|---:|---:|---|---|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        sc = next((c for c in r['checks'] if c['name']=='SELF_CORRELATION'), {})
        conc_ok = conc.get('result')=='PASS'
        sub_ok = sub.get('result')=='PASS'
        all_pass = (r['sharpe']>=1.5 and r['turnover']<0.20 and conc_ok and sub_ok)
        if all_pass: survivors.append(r)
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {sc.get('value','-')} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | - | no |  "
               f"{r.get('error','?')[:80]}\n")
    md += f"\n**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): {len(survivors)}/{len(results)}**\n"
    if survivors:
        md += "\n## Survivor expressions\n\n"
        for r in survivors:
            md += (f"### {r['variant']} -- alpha {r.get('alpha_id','?')}\n"
                   f"SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
                   f"FIT={r['fitness']:+.3f}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
