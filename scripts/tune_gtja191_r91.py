"""Round 91: orthogonal close-based bases at p=2.5 d=15.

The MA60_rev shape is exhausted -- conc-PASS hard cap at SH ~1.19.
Try structurally different mean-reversion signals at same transform:

  R91a  MA20/MA60 ratio (MACD-style)         signed_power(z(rev(MA20/MA60)), 2.5)
  R91b  ts_zscore(close, 60) reversed         z-based reversion
  R91c  MA20 reversion + p=2.5                shorter mean window
  R91d  outer zscore REMOVED                   ts_decay_linear(p25_core, 15) only
  R91e  power AFTER smoothing                  signed_power(z(ts_decay(rev_MA60,15)), 2.5)
  R91f  log(close/MA60) + p=2.5                log-return reversion
  R91g  ts_rank(close, 60) reversed + p=2.5    rank-based reversion
  R91h  vol-adjusted MA60 reversion            divide(reverse_ret, std)

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r91")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(neutralization: str = "SUBINDUSTRY", truncation: float = 0.08) -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": truncation,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


def PV(z_core: str, p: float = 2.5) -> str:
    return f"signed_power(zscore({z_core}), {p})"


# R91a MACD-style: short MA / long MA, reversed (mean revert from spread)
R91a = W(PV("reverse(divide(ts_mean(close, 20), ts_mean(close, 60)))"), 15)

# R91b ts_zscore(close,60) reversed
R91b = W(PV("reverse(ts_zscore(close, 60))"), 15)

# R91c MA20 reversion
R91c = W(PV("reverse(divide(close, ts_mean(close, 20)))"), 15)

# R91d outer zscore removed
R91d = f"ts_decay_linear({PV('reverse(divide(close, ts_mean(close, 60)))')}, 15)"

# R91e power AFTER smoothing
R91e = f"signed_power(zscore(ts_decay_linear(reverse(divide(close, ts_mean(close, 60))), 15)), 2.5)"

# R91f log-return MA reversion
R91f = W(PV("reverse(log(divide(close, ts_mean(close, 60))))"), 15)

# R91g ts_rank(close,60) reversed
R91g = W(PV("reverse(ts_rank(close, 60))"), 15)

# R91h vol-adjusted: (close - MA60) / std(close, 60), reversed
R91h = W(PV("reverse(divide(subtract(close, ts_mean(close, 60)), ts_std_dev(close, 60)))"), 15)

VARIANTS = [
    {"label": "R91a_MACD_short_long",         "expression": R91a, "settings": settings()},
    {"label": "R91b_tszscore60_rev",          "expression": R91b, "settings": settings()},
    {"label": "R91c_MA20_rev_p25",            "expression": R91c, "settings": settings()},
    {"label": "R91d_no_outer_zscore",         "expression": R91d, "settings": settings()},
    {"label": "R91e_power_after_smooth",      "expression": R91e, "settings": settings()},
    {"label": "R91f_log_MA60_rev",            "expression": R91f, "settings": settings()},
    {"label": "R91g_tsrank60_rev_p25",        "expression": R91g, "settings": settings()},
    {"label": "R91h_voladj_MA60_rev",         "expression": R91h, "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r91_orthogonal_bases_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R91: try structurally different mean-reversion bases at p=2.5 d=15 to break MA60 ceiling.\n"
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
    md = "# R91 orthogonal bases\n\n"
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
