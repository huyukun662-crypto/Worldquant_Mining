"""Round 63: structurally novel skeletons (target SH>=1.5 ^ TO<0.20).

Prior rounds covered acceleration (R15/R16/R28/R29), realized vol /
ts_std_dev (R45/R46/R47), iv_skew (R19-R21), fundamental fscore/eps/
analyst/sentiment/model (R30-R44), reverse_inside / diff_skeletons
(R52/R53), news_impact (R56-R62). This round tries 8 skeletons that
were NOT deeply mined and that are structurally distinct from the
above:

  AA  Amihud illiquidity    |returns| / (close * volume)
  BB  Garman-Klass range    log(high/low)^2 averaged
  CC  Return skewness       ts_skewness(returns, 20)
  DD  Drawdown signal       (close - ts_max(close, 60)) / ts_max(close, 60)
  EE  Vol of vol            ts_std_dev(ts_std_dev(returns, 5), 40)
  FF  Rolling self-Sharpe   ts_mean(returns,20) / ts_std_dev(returns,20)
  GG  Price-VWAP gap        (close - vwap) / vwap
  HH  Directional efficiency net_move / sum(|moves|)  (signed by net move)

All wrapped: zscore(ts_decay_linear(<core>, 30)), TOP3000, delay=1,
decay=8, truncation=0.08, SUBINDUSTRY, pasteurization ON. Same hard
gate as the news round: SH >= 1.5 ^ TO < 0.20 ^ conc+sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r63")
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


# 1. Amihud illiquidity, reversed (illiquid -> overpriced -> short)
AA = W(f"reverse(ts_mean(divide(abs(returns), add(multiply(close, volume), 1)), 20))")
# 2. Garman-Klass range vol, reversed (high range -> mean-revert)
BB = W(f"reverse(ts_mean(signed_power(log(divide(high, low)), 2), 20))")
# 3. Return skewness, reversed (positive-skew lottery -> short)
CC = W(f"reverse(ts_skewness(returns, 20))")
# 4. Drawdown signal: distance below rolling max (natural sign:
#    close at peak -> 0, deeply below -> negative; reverse so deep
#    drawdown -> positive expected rebound)
DD = W(f"reverse(divide(subtract(close, ts_max(close, 60)), ts_max(close, 60)))")
# 5. Vol-of-vol, reversed (vol-vol -> uncertain -> short premium)
EE = W(f"reverse(ts_std_dev(ts_std_dev(returns, 5), 40))")
# 6. Rolling self-Sharpe (natural: high SH -> momentum continuation)
FF = W(f"divide(ts_mean(returns, 20), add(ts_std_dev(returns, 20), 0.001))")
# 7. Price-VWAP gap, reversed (close above vwap intraday -> overbought)
GG = W(f"reverse(divide(subtract(close, vwap), vwap))")
# 8. Directional efficiency * net move (trend-purity weighted momentum)
HH = W(
    f"multiply(ts_delta(close, 20), "
    f"divide(abs(ts_delta(close, 20)), add(ts_sum(abs(ts_delta(close, 1)), 20), 0.001)))"
)

VARIANTS = [
    {"label": "AA_amihud_illiq_rev", "expression": AA},
    {"label": "BB_gk_range_rev", "expression": BB},
    {"label": "CC_skew_returns_rev", "expression": CC},
    {"label": "DD_drawdown60_rev", "expression": DD},
    {"label": "EE_vol_of_vol_rev", "expression": EE},
    {"label": "FF_rolling_self_sharpe", "expression": FF},
    {"label": "GG_price_vwap_gap_rev", "expression": GG},
    {"label": "HH_directional_efficiency", "expression": HH},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r63_novel_skeletons_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R63: 8 structurally novel skeletons (Amihud / range-vol / skewness "
        "/ drawdown / vol-of-vol / rolling-Sharpe / price-VWAP / directional "
        "efficiency). Gate: SH>=1.5 ^ TO<0.20 ^ conc+sub PASS.\n"
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
    md = "# R63 novel skeletons (target SH>=1.5 ^ TO<0.20)\n\n"
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
