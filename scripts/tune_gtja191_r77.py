"""Round 77: pure-PV GTJA191 alphas (no close, no open, no returns).

User constraint: avoid close and open fields. By extension, avoid
`returns` (close-derived). Allowed fields: high, low, volume, adv20,
vwap. This is the most-unexplored slice of GTJA191 in our campaign.

Already mined: BB Garman-Klass (uses high/low), shipped A1nnxAdw.
The remaining pure-PV GTJA191 skeletons that pass our op filter:

  R77a  alpha_13   sqrt(H*L) - VWAP                       (geo mean vs VWAP)
  R77b  alpha_42   rank(std(H,10)) * corr(H, V, 10)
  R77c  alpha_62   -corr(H, rank(V), 5)
  R77d  alpha_90   -rank(corr(rank(VWAP), rank(V), 5))
  R77e  alpha_109  decay(H-L,10) / decay(decay(H-L,10),10)
  R77f  alpha_141  -rank(corr(rank(H), rank(mean(V,15)), 9))
  R77g  alpha_177  days-since-20d-high reversed
  R77h  range-TS   (5d range) / (60d range), reversed

Settings: TOP3000, delay=1, decay=8, trunc=0.08, SUBINDUSTRY, pasteur ON.
Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7 vs
A1nnxAdw + TT3 (9q9o0zme) which are now both ACTIVE.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r77")
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


R77a = W(f"subtract(signed_power(multiply(high, low), 0.5), vwap)")
R77b = W(f"multiply(rank(ts_std_dev(high, 10)), ts_corr(high, volume, 10))")
R77c = W(f"multiply(-1, ts_corr(high, rank(volume), 5))")
R77d = W(f"multiply(-1, rank(ts_corr(rank(vwap), rank(volume), 5)))")
HL = "subtract(high, low)"
R77e = W(f"divide(ts_decay_linear({HL}, 10), ts_decay_linear(ts_decay_linear({HL}, 10), 10))")
R77f = W(f"multiply(-1, rank(ts_corr(rank(high), rank(ts_mean(volume, 15)), 9)))")
R77g = W(f"reverse(ts_arg_max(high, 20))")
R77h = W(f"reverse(divide(ts_mean({HL}, 5), ts_mean({HL}, 60)))")


VARIANTS = [
    {"label": "R77a_G13_sqrtHL_minus_vwap", "expression": R77a},
    {"label": "R77b_G42_rankStdH_corrHV",   "expression": R77b},
    {"label": "R77c_G62_neg_corrH_rankV",   "expression": R77c},
    {"label": "R77d_G90_neg_rank_corrRV",   "expression": R77d},
    {"label": "R77e_G109_range_smooth_ratio","expression": R77e},
    {"label": "R77f_G141_neg_rank_corrHV",  "expression": R77f},
    {"label": "R77g_G177_dayssince_high_rev","expression": R77g},
    {"label": "R77h_range_TS_5o60_rev",     "expression": R77h},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r77_purePV_no_close_open_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R77: pure-PV GTJA191 (only high/low/volume/vwap/adv20; no "
        "close/open/returns). Targets families uncorrelated with "
        "A1nnxAdw (BB) and TT3 (rv-accel).\n"
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
    md = "# R77 pure PV (no close/open/returns)\n\n"
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
