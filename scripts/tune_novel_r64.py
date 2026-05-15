"""Round 64: amplify R63's BB winner + fix the broken variants.

R63 outcome:
  BB Garman-Klass range vol -> SH +1.31  TO 0.053  FIT +2.38, all checks PASS.
    Cleanest TO of the campaign. Just under the 1.5 SH gate.
  4 fails (unit errors on `add(., constant)` or blocked operators
    ts_skewness, ts_max on this account tier).
  3 weak signals (EE vol-of-vol, FF rolling SH, GG price-VWAP).

R64 strategy:
  1. Amplify BB: longer decay, combo with reverse-momentum, combo with
     log-volume scaling, longer window.
  2. Fix the unit-error variants by replacing `add(x, unitless_const)`
     with `divide(x, unitful_baseline)`.
  3. Replace the blocked-operator variants:
     ts_skewness -> ts_moment(returns, 20, 3) if accessible.
     ts_max(close, N) -> ts_zscore(close, N) (distance-from-mean proxy)
                       and (close - vwap60-ish) options.
  4. Add intraday-range "close-in-range" as a fresh PV skeleton.

Same hard gate: SH >= 1.5 ^ TO < 0.20 ^ conc+sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r64")
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


GK_W20 = "ts_mean(signed_power(log(divide(high, low)), 2), 20)"
GK_W60 = "ts_mean(signed_power(log(divide(high, low)), 2), 60)"
REV_MOM5 = "reverse(ts_zscore(returns, 5))"
VOLWT = "log(divide(volume, adv20))"  # zero-centered, unitless safe inside multiply

# II  BB with stronger decay
II = W(f"reverse({GK_W20})", decay=60)
# JJ  BB * reverse 5d momentum
JJ = W(f"multiply(reverse({GK_W20}), {REV_MOM5})", decay=30)
# KK  BB * log relative volume
KK = W(f"multiply(reverse({GK_W20}), {VOLWT})", decay=30)
# LL  Amihud illiq via ratio (no unitless add)
LL = W(
    f"reverse(divide(ts_mean(abs(returns), 20), "
    f"ts_mean(multiply(close, volume), 20)))",
    decay=30,
)
# MM  Drawdown proxy via close z-score (no ts_max)
MM = W(f"reverse(ts_zscore(close, 60))", decay=30)
# NN  Skewness via ts_moment(., d, k=3); if blocked we'll see the error
NN = W(f"reverse(ts_moment(returns, 20, 3))", decay=30)
# OO  BB longer window
OO = W(f"reverse({GK_W60})", decay=60)
# PP  Close position within daily range (no constants in denominator;
#     subtract(high,low)==0 days will be NaN-dropped under nanHandling)
PP = W(
    f"reverse(ts_mean(divide(subtract(close, low), subtract(high, low)), 20))",
    decay=30,
)

VARIANTS = [
    {"label": "II_BB_decay60", "expression": II},
    {"label": "JJ_BB_x_revmom5", "expression": JJ},
    {"label": "KK_BB_x_logvol", "expression": KK},
    {"label": "LL_amihud_ratio", "expression": LL},
    {"label": "MM_close_zscore60_rev", "expression": MM},
    {"label": "NN_skew_via_moment3", "expression": NN},
    {"label": "OO_BB_w60_D60", "expression": OO},
    {"label": "PP_close_in_range_rev", "expression": PP},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r64_amplify_bb_fixes_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R64: amplify R63's BB Garman-Klass range winner (SH 1.31 / TO 0.053) "
        "via longer decay/window and combo with momentum/volume; fix the 4 "
        "unit/operator errors. Gate: SH>=1.5 ^ TO<0.20 ^ conc+sub PASS.\n"
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
    md = "# R64 amplify BB + fix unit/operator errors\n\n"
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
