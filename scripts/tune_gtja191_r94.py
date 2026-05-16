"""Round 94: pivot off MA60_PV6 family. 8 fresh structures + new operators.

Account success pattern (A1nnxAdw, 9q9o0zme both vol-based) suggests
volatility estimators are the high-quality space. R94 explores:

  R94a  Parkinson vol mean-rev               ln(H/L)^2 -> ts_mean -> reverse -> p25
  R94b  Rogers-Satchell vol estimator         ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O)
  R94c  Returns skewness reversed             ts_skewness(returns, 60) -- new op
  R94d  Returns kurtosis reversed             ts_kurtosis(returns, 60) -- new op
  R94e  Industry-relative close               cross-sec spread vs group_mean
  R94f  Overnight gap momentum                open/ts_delay(close,1) -- gap effect
  R94g  vector_neut market-residual           vector_neut(returns, group_returns)
  R94h  ATR-relative move                     |return| / (H-L) -- range-norm signal

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r94")
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


def PV25(z_core: str) -> str:
    return f"signed_power(zscore({z_core}), 2.5)"


# R94a Parkinson vol = (1/4ln2) * ln(H/L)^2. Use 60d mean of squared log range.
PARK = "ts_mean(power(log(divide(high, low)), 2), 60)"
R94a = W(PV25(f"reverse({PARK})"))

# R94b Rogers-Satchell vol estimator (no close-vs-prev dependency, intraday only)
RS = "add(multiply(log(divide(high, close)), log(divide(high, open))), multiply(log(divide(low, close)), log(divide(low, open))))"
R94b = W(PV25(f"reverse(ts_mean({RS}, 60))"))

# R94c returns ts_skewness reversed (low skew = recent crashes -> mean rev up)
R94c = W(PV25("reverse(ts_skewness(returns, 60))"))

# R94d returns ts_kurtosis reversed (high kurt = tail-driven, fade)
R94d = W(PV25("reverse(ts_kurtosis(returns, 60))"))

# R94e industry-relative close (cross-sectional spread)
R94e = W(PV25("reverse(divide(close, group_mean(close, 1, industry)))"))

# R94f overnight gap effect: open / prev_close, reversed (gap fade)
R94f = W(PV25("reverse(divide(open, ts_delay(close, 1)))"))

# R94g vector_neut market-residual returns: residualize returns vs industry mean returns
R94g = W(PV25("reverse(vector_neut(returns, group_mean(returns, 1, industry)))"))

# R94h ATR-relative absolute move: |return| / range (intraday vol-normalized momentum)
R94h = W(PV25("reverse(divide(abs(returns), divide(subtract(high, low), close)))"))

VARIANTS = [
    {"label": "R94a_parkinson_vol_rev",   "expression": R94a, "settings": settings()},
    {"label": "R94b_rogers_satchell_rev", "expression": R94b, "settings": settings()},
    {"label": "R94c_skewness_rev",        "expression": R94c, "settings": settings()},
    {"label": "R94d_kurtosis_rev",        "expression": R94d, "settings": settings()},
    {"label": "R94e_industry_rel_close",  "expression": R94e, "settings": settings()},
    {"label": "R94f_overnight_gap_fade",  "expression": R94f, "settings": settings()},
    {"label": "R94g_vector_neut_returns", "expression": R94g, "settings": settings()},
    {"label": "R94h_atr_rel_abs_move",    "expression": R94h, "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r94_fresh_structures_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R94: pivot off MA60_PV6 family. 8 fresh structures (vol estimators, "
        "skewness/kurtosis, cross-sectional spreads, gap, vector_neut, ATR-rel).\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression'][:140]}...")
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
    md = "# R94 fresh structures\n\n"
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
        all_pass = (r['sharpe']>=1.25 and r['turnover']<0.20 and conc_ok and sub_ok)
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
    md += f"\n**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS): {len(survivors)}/{len(results)}**\n"
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
