"""Round 79: new no-close/open skeletons (PV6 amp didn't lift rank-corr bases).

R78 lesson: PV6 amplification adds +0.0 to +0.2 SH on rank-correlation
bases (G62/G90/G141) because those are already bounded in [-1, 1] --
no heavy tails to amplify. Range_TS got +0.20 (unbounded ratio).

To find a new survivor without close/open/returns, try fundamentally
different skeletons that aren't pre-bounded:

  R79a  20d HIGH momentum reversed
  R79b  20d VWAP momentum reversed
  R79c  VWAP return std-dev 20d reversed (vol proxy without close)
  R79d  (H-L) x volume correlation
  R79e  VWAP cross-time zscore 60 reversed
  R79f  VWAP zscore x range combo
  R79g  relative-volume momentum (vol/mean(vol,20))
  R79h  log(range) zscore reversed -- gentler than BB squared

All wrapped: zscore(ts_decay_linear(<core>, 30)).
Settings: USA TOP3000 delay=1 decay=8 trunc=0.08 SUBINDUSTRY pasteur ON.
Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7 vs
A1nnxAdw + 9q9o0zme.
DO NOT auto-submit -- only print; manual verify before submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r79")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings() -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": 0.08,
        "neutralization": "SUBINDUSTRY", "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


# VWAP daily return
VWAP_RET1 = "divide(subtract(vwap, ts_delay(vwap, 1)), ts_delay(vwap, 1))"

R79a = W(f"reverse(divide(subtract(high, ts_delay(high, 20)), ts_delay(high, 20)))")
R79b = W(f"reverse(divide(subtract(vwap, ts_delay(vwap, 20)), ts_delay(vwap, 20)))")
R79c = W(f"reverse(ts_std_dev({VWAP_RET1}, 20))")
R79d = W(f"ts_corr(subtract(high, low), volume, 10)")
R79e = W(f"reverse(ts_zscore(vwap, 60))")
R79f = W(f"multiply(ts_zscore(vwap, 20), subtract(high, low))")
R79g = W(f"ts_delta(divide(volume, ts_mean(volume, 20)), 10)")
R79h = W(f"reverse(ts_zscore(log(divide(high, low)), 60))")


VARIANTS = [
    {"label": "R79a_high_mom20_rev",   "expression": R79a},
    {"label": "R79b_vwap_mom20_rev",   "expression": R79b},
    {"label": "R79c_vwap_ret_vol_rev", "expression": R79c},
    {"label": "R79d_HL_vol_corr",      "expression": R79d},
    {"label": "R79e_vwap_zscore60_rev","expression": R79e},
    {"label": "R79f_vwap_x_range",     "expression": R79f},
    {"label": "R79g_relvol_delta10",   "expression": R79g},
    {"label": "R79h_logHL_zscore60_rev","expression": R79h},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r79_no_close_open_new_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R79: new no-close/open skeletons; high/VWAP momentum, "
        "VWAP-ret vol, range x volume corr, etc.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], settings())
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"], **res}
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
    md = "# R79 no-close/open new skeletons\n\n"
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
