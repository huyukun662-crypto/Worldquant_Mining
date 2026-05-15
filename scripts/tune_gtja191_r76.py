"""Round 76: PV6 recipe on volume-volatility GTJA bases + overnight-gap BB analog.

R75 result: best conc-PASS variant was EE5 (G158 zscore-IN pow 3 +
trunc 0.03) at SH 1.33 -- structurally below the 1.5 gate. G158
cube can't simultaneously clear SH and conc on this account.

Strategy: try different bases whose distribution may respond more
favorably to PV6 amplification. Bases: dollar-volume volatility
(GTJA070, 095), volume volatility (GTJA097, 100), and overnight log
gap squared (a BB analog whose daily PnL should be orthogonal to
the intraday-range A1nnxAdw).

  FF1  G070 (std amount 6d)   PV6 recipe
  FF2  G095 (std amount 20d)  PV6 recipe
  FF3  G097 (std volume 10d)  PV6 recipe
  FF4  G100 (std volume 20d)  PV6 recipe
  FF5  Overnight log gap^2 (BB analog) -- intraday range -> overnight
  FF6  GTJA109 (H-L decay ratio) PV6
  FF7  G070 zscore-IN + pow 3                 stronger amp
  FF8  G158 zscore-IN + pow 3 + INDUSTRY      alt to EE5

Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7 vs A1nnxAdw.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r76")
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


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


# Bases (raw, NOT pre-reversed -- direction decided below per base)
G070 = "ts_std_dev(multiply(close, volume), 6)"
G095 = "ts_std_dev(multiply(close, volume), 20)"
G097 = "ts_std_dev(volume, 10)"
G100 = "ts_std_dev(volume, 20)"
# Overnight gap squared, smoothed 20d
OG = "signed_power(log(divide(open, ts_delay(close, 1))), 2)"
OG20 = f"ts_mean({OG}, 20)"
# GTJA109 H-L decay ratio
HL = "subtract(high, low)"
G109 = f"divide(ts_decay_linear({HL}, 10), ts_decay_linear(ts_decay_linear({HL}, 10), 10))"
# G158 again for FF8
MA15 = "ts_decay_linear(close, 15)"
G158 = f"reverse(divide(subtract(subtract(high, {MA15}), subtract(low, {MA15})), close))"


def pv6(core_reversed: str) -> str:
    return W(f"signed_power(zscore({core_reversed}), 2)")


FF1 = pv6(f"reverse({G070})")
FF2 = pv6(f"reverse({G095})")
FF3 = pv6(f"reverse({G097})")
FF4 = pv6(f"reverse({G100})")
FF5 = pv6(f"reverse({OG20})")
FF6 = pv6(f"reverse({G109})")
FF7 = W(f"signed_power(zscore(reverse({G070})), 3)")  # cube
FF8 = W(f"signed_power(zscore({G158}), 3)")


VARIANTS = [
    {"label": "FF1_G070_PV6",          "expression": FF1, "settings": settings()},
    {"label": "FF2_G095_PV6",          "expression": FF2, "settings": settings()},
    {"label": "FF3_G097_PV6",          "expression": FF3, "settings": settings()},
    {"label": "FF4_G100_PV6",          "expression": FF4, "settings": settings()},
    {"label": "FF5_OVgap_PV6",         "expression": FF5, "settings": settings()},
    {"label": "FF6_G109_PV6",          "expression": FF6, "settings": settings()},
    {"label": "FF7_G070_zIN_pow3",     "expression": FF7, "settings": settings()},
    {"label": "FF8_G158_zIN_pow3_IND", "expression": FF8,
     "settings": settings(truncation=0.03, neutralization="INDUSTRY")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r76_vol_vol_bases_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R76: PV6 recipe on volume-volatility GTJA bases + overnight-gap BB analog.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        log.info(f"      trunc={v['settings']['truncation']} "
                 f"neut={v['settings']['neutralization']}")
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
    md = "# R76 volume-volatility bases\n\n"
    md += ("| variant | trunc | neut | SH | TO | FIT | checks | conc | sub | gate |\n"
           "|---|---:|---|---:|---:|---:|---|---|---|---|\n")
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
        s_ = r['settings']
        md += (f"| {r['variant']} | {s_['truncation']} | {s_['neutralization']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | - | - | FAIL | - | - | - | - | - | no |  "
               f"{r.get('error','?')[:80]}\n")
    md += f"\n**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): {len(survivors)}/{len(results)}**\n"
    if survivors:
        md += "\n## Survivor expressions\n\n"
        for r in survivors:
            md += (f"### {r['variant']} -- alpha {r.get('alpha_id','?')}\n"
                   f"SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
                   f"FIT={r['fitness']:+.3f}\n"
                   f"settings: {json.dumps({k:v for k,v in r['settings'].items() if k in ('universe','truncation','neutralization')})}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
