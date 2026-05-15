"""Round 70: GTJA191 first batch (8 structurally distinct skeletons).

Per user instruction "use the factor library mentioned in the Zhihu
article (GTJA191 + JoinQuant)". This round samples 8 GTJA191 alphas
that are NOT already covered by prior rounds (no pure momentum,
rv-acceleration, news_impact, or BB range-vol):

  GTJA002  reverse(ts_delta((CLOSE-LOW-(HIGH-CLOSE))/(HIGH-LOW), 1))
  GTJA015  (OPEN - prev CLOSE) / prev CLOSE                 (overnight gap)
  GTJA029  6d returns x volume                              (vol-weighted mom)
  GTJA043  ts_sum(sign(d_close) * volume, 6)                (signed volume)
  GTJA053  ts_sum(greater(close, prev close), 12)           (up-day count)
  GTJA070  reverse(ts_std_dev(close * volume, 6))           (dollar-vol vol)
  GTJA103  reverse(ts_arg_min(low, 20))                     (days-since-low)
  GTJA120  reverse(rank(VWAP-CLOSE) / rank(VWAP+CLOSE))     (VWAP polarization)

All wrapped: zscore(ts_decay_linear(<core>, 8)).
Settings: TOP3000, delay=1, decay=8, trunc=0.08, SUBINDUSTRY, pasteur ON.
Gate: SH >= 1.5 ^ TO < 0.20 ^ ALL 8 WQ checks PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r70")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(truncation: float = 0.08,
             neutralization: str = "SUBINDUSTRY",
             universe: str = "TOP3000") -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": universe,
        "delay": 1, "decay": 8, "truncation": truncation,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 8) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


PRICE_POS = "divide(subtract(subtract(close, low), subtract(high, close)), subtract(high, low))"
RET6 = "divide(subtract(close, ts_delay(close, 6)), ts_delay(close, 6))"
SGN_DC = "sign(subtract(close, ts_delay(close, 1)))"
UPDAY = "greater(close, ts_delay(close, 1))"
GAP = "divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1))"
VWAP_POL = "divide(rank(subtract(vwap, close)), rank(add(vwap, close)))"

GTJA002 = W(f"reverse(ts_delta({PRICE_POS}, 1))")
GTJA015 = W(f"{GAP}")
GTJA029 = W(f"multiply({RET6}, volume)")
GTJA043 = W(f"ts_sum(multiply({SGN_DC}, volume), 6)")
GTJA053 = W(f"ts_sum({UPDAY}, 12)")
GTJA070 = W(f"reverse(ts_std_dev(multiply(close, volume), 6))")
GTJA103 = W(f"reverse(ts_arg_min(low, 20))")
GTJA120 = W(f"reverse({VWAP_POL})")

VARIANTS = [
    {"label": "GTJA002_dpos_rev",        "expression": GTJA002},
    {"label": "GTJA015_overnight_gap",   "expression": GTJA015},
    {"label": "GTJA029_volwt_mom6",      "expression": GTJA029},
    {"label": "GTJA043_signed_vol6",     "expression": GTJA043},
    {"label": "GTJA053_upday_frac12",    "expression": GTJA053},
    {"label": "GTJA070_dollarvol_vol_rev","expression": GTJA070},
    {"label": "GTJA103_daysince_low_rev","expression": GTJA103},
    {"label": "GTJA120_vwap_polar_rev",  "expression": GTJA120},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r70_gtja191_batch1_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R70: GTJA191 batch 1 -- 8 distinct skeletons. Gate: SH>=1.5 ^ "
        "TO<0.20 ^ all 8 WQ checks PASS.\n"
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
    md = "# R70 GTJA191 batch 1\n\n"
    md += ("| variant | SH | TO | FIT | checks | conc | sub | gate |\n"
           "|---|---:|---:|---:|---|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        conc_ok = conc.get('result')=='PASS'
        sub_ok = sub.get('result')=='PASS'
        all_pass = (r['sharpe']>=1.5 and r['turnover']<0.20 and conc_ok and sub_ok)
        if all_pass: survivors.append(r)
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | no |  "
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
