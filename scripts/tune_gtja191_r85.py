"""Round 85: close-allowed re-entry. After 8 rounds of no-close/open
hitting SH ~1.00 ceiling, user permits returning to close-based
candidates. Avoid SC with existing portfolio:

  A1nnxAdw -- BB GK range vol on high/low only
  9q9o0zme -- rv x acceleration x volume

So pick close angles that are structurally different from those.

R85a  20d close return reversed + PV6                long-term mean-rev
R85b  MA60 reversion + PV6                            classical reversion
R85c  close/vwap ratio + PV6                          intraday close pos
R85d  ts_zscore(close,60) reversed + PV6              close z-score rev
R85e  Bollinger %B reversed + PV6                     bb-position rev
R85f  delta(close)*volume + PV6                       VW return
R85g  close/ts_max(close,60) reversed + PV6           dist-from-high
R85h  ts_corr(close, volume, 20) signed_power         close-vol corr

Gate: SH>=1.5, TO<0.20, conc+sub PASS, SC<0.7 against A1nnxAdw/9q9o0zme.
DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r85")
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


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


def pv6(z_core: str) -> str:
    return f"signed_power(zscore({z_core}), 2)"


# inner cores (close-based, reversed for mean-reversion direction)
R85a_core = pv6("reverse(divide(subtract(close, ts_delay(close, 20)), ts_delay(close, 20)))")
R85b_core = pv6("reverse(divide(close, ts_mean(close, 60)))")
R85c_core = pv6("divide(close, vwap)")
R85d_core = pv6("reverse(ts_zscore(close, 60))")
R85e_core = pv6("reverse(divide(subtract(close, ts_mean(close, 20)), ts_std_dev(close, 20)))")
R85f_core = pv6("multiply(subtract(close, ts_delay(close,1)), volume)")
R85g_core = pv6("reverse(divide(close, ts_max(close, 60)))")
R85h_core = pv6("ts_corr(close, volume, 20)")


VARIANTS = [
    {"label": "R85a_close_ret20_rev_PV6",    "expression": W(R85a_core), "settings": settings()},
    {"label": "R85b_MA60_reversion_PV6",     "expression": W(R85b_core), "settings": settings()},
    {"label": "R85c_close_over_vwap_PV6",    "expression": W(R85c_core), "settings": settings()},
    {"label": "R85d_zscore_close_rev_PV6",   "expression": W(R85d_core), "settings": settings()},
    {"label": "R85e_bollinger_pct_rev_PV6",  "expression": W(R85e_core), "settings": settings()},
    {"label": "R85f_VW_return_PV6",          "expression": W(R85f_core), "settings": settings()},
    {"label": "R85g_dist_from_60d_high_PV6", "expression": W(R85g_core), "settings": settings()},
    {"label": "R85h_close_vol_corr20_PV6",   "expression": W(R85h_core), "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r85_close_allowed_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R85: close re-allowed after 8 rounds of no-close/open ceiling. "
        "Aim: diverse close-based angles avoiding SC with A1nnxAdw + 9q9o0zme.\n"
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
    md = "# R85 close-allowed re-entry\n\n"
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
        md += (f"| {r['variant']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
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
