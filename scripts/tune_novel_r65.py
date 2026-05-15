"""Round 65: 8 more truly different skeletons.

R63 found BB Garman-Klass range vol = SH 1.31 / TO 0.053 / FIT 2.38.
R64 confirmed BB has a hard SH ~1.32 plateau (longer window/decay
identical; combos with rev-momentum and log-volume destructively
flip the sign).

This round tries 8 different skeletons that have NOT been mined:

  QQ  Full Garman-Klass     log(H/L)^2 - log(C/O)^2   (adds overnight gap)
  RR  Range term structure  range(5) / range(60)
  SS  Overnight gap vol     ts_mean(log(O/prev_C)^2, 20)
  TT  Intraday vs overnight log(C/O) - log(O/prev_C)
  UU  Price-volume corr     ts_corr(ts_delta(close,1), volume, 20)
  VV  Days-since-low        reverse(ts_arg_min(low, 60))
  WW  Range expansion       (today range) / (avg range 20)
  XX  Close vs midrange     (2*close - (H+L)) / (H-L)

Same gate: SH >= 1.5 ^ TO < 0.20 ^ conc+sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r65")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def base_settings() -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": 0.08,
        "neutralization": "SUBINDUSTRY", "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


RANGE_SQ = "signed_power(log(divide(high, low)), 2)"
CO_SQ = "signed_power(log(divide(close, open)), 2)"
OPC_SQ = "signed_power(log(divide(open, ts_delay(close, 1))), 2)"

# QQ Full Garman-Klass-like: log(H/L)^2 - log(C/O)^2 (both unit-clean)
QQ = W(f"reverse(ts_mean(subtract({RANGE_SQ}, {CO_SQ}), 20))", decay=30)
# RR Range term structure: short-vol / long-vol, reversed (spike -> mean revert)
RR = W(
    f"reverse(divide(ts_mean({RANGE_SQ}, 5), ts_mean({RANGE_SQ}, 60)))",
    decay=30,
)
# SS Overnight gap vol, reversed
SS = W(f"reverse(ts_mean({OPC_SQ}, 20))", decay=30)
# TT Intraday vs overnight return contrast (mean over 20d)
TT = W(
    f"ts_mean(subtract(log(divide(close, open)), "
    f"log(divide(open, ts_delay(close, 1)))), 20)",
    decay=30,
)
# UU Price-change-volume correlation (info-trading proxy)
UU = W(f"ts_corr(ts_delta(close, 1), volume, 20)", decay=30)
# VV Days-since-most-recent-low (recency); reverse so recent low -> high signal
VV = W(f"reverse(ts_arg_min(low, 60))", decay=30)
# WW Range expansion: today's range / 20d avg range, reversed
WW = W(
    f"reverse(divide(subtract(high, low), "
    f"ts_mean(subtract(high, low), 20)))",
    decay=30,
)
# XX Close vs mid-range: (2c - (h+l)) / (h-l), reversed
XX = W(
    f"reverse(divide(subtract(multiply(2, close), add(high, low)), "
    f"subtract(high, low)))",
    decay=30,
)

VARIANTS = [
    {"label": "QQ_full_gk_open_term", "expression": QQ},
    {"label": "RR_range_term_structure", "expression": RR},
    {"label": "SS_overnight_gap_vol", "expression": SS},
    {"label": "TT_intraday_vs_overnight", "expression": TT},
    {"label": "UU_price_volume_corr", "expression": UU},
    {"label": "VV_days_since_low_rev", "expression": VV},
    {"label": "WW_range_expansion_rev", "expression": WW},
    {"label": "XX_close_vs_midrange_rev", "expression": XX},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r65_more_skeletons_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R65: 8 more skeletons after BB plateau (full GK / range term "
        "structure / overnight gap / intraday-vs-overnight / price-vol "
        "corr / days-since-low / range expansion / close-vs-midrange). "
        "Gate: SH>=1.5 ^ TO<0.20 ^ conc+sub PASS.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        settings = base_settings()
        try:
            res = r5.submit(cm.session, v["expression"], settings)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"], **res}
        results.append(entry)
        (session_dir / "working" / "results_partial.json").write_text(
            json.dumps(results, indent=2))
        if res.get("ok"):
            log.info(f"      SH={res['sharpe']:+.3f} TO={res['turnover']:.3f} "
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT","LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")
    md = "# R65 more skeletons (post-BB plateau)\n\n"
    md += ("| variant | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---:|---:|---:|---|---|---|\n")
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
                f"{r['fitness']:+.3f} | {c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | no |  "
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
