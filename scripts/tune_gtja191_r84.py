"""Round 84: last-resort no-close/open angles -- longer windows, term-
structure differentials, trade_when gating, composite winners.

After R77-R83 ceiling at SH ~1.00 conc PASS, R84 tries:

  R84a  VWAPmom90 + PV6                             very long window
  R84b  VWAPmom120 + PV6                            even longer
  R84c  (VWAPmom20 - VWAPmom60) + PV6               term-structure diff
  R84d  trade_when(|VWAPmom20|>0.05, VWAPmom_PV6, -1)  large-signal only
  R84e  VWAPmom20 x relvol60                         vol-modulated mom
  R84f  VWAPmom60 + PV6 + INDUSTRY (R83g + R81b combo wins)
  R84g  days-since-VWAP-max + PV6                    arg_max(vwap,60) rev
  R84h  weighted multi-window sum 20+60+120          smooth composite

Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7.
DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r84")
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


def vwret(n: int) -> str:
    return f"divide(subtract(vwap, ts_delay(vwap, {n})), ts_delay(vwap, {n}))"


VWAP_RET20 = vwret(20)
VWAP_RET60 = vwret(60)
VWAP_RET90 = vwret(90)
VWAP_RET120 = vwret(120)
RELVOL60 = "divide(volume, ts_mean(volume, 60))"


def pv6_rev(src: str) -> str:
    return W(f"signed_power(zscore(reverse({src})), 2)")


R84a = pv6_rev(VWAP_RET90)
R84b = pv6_rev(VWAP_RET120)
R84c = pv6_rev(f"subtract({VWAP_RET20}, {VWAP_RET60})")
PV6_VWAPMOM = f"signed_power(zscore(reverse({VWAP_RET20})), 2)"
R84d = W(f"trade_when(greater(abs({VWAP_RET20}), 0.05), {PV6_VWAPMOM}, -1)")
R84e = W(f"signed_power(zscore(multiply(reverse({VWAP_RET20}), {RELVOL60})), 2)")
R84f = pv6_rev(VWAP_RET60)  # uses INDUSTRY via settings override
R84g = W(f"signed_power(zscore(reverse(ts_arg_max(vwap, 60))), 2)")
# weighted sum 20+60+120 (all reversed for direction)
W84h_core = (
    f"add(add(reverse({VWAP_RET20}), reverse({VWAP_RET60})), reverse({VWAP_RET120}))"
)
R84h = W(f"signed_power(zscore({W84h_core}), 2)")


VARIANTS = [
    {"label": "R84a_VWAPmom90_PV6",       "expression": R84a, "settings": settings()},
    {"label": "R84b_VWAPmom120_PV6",      "expression": R84b, "settings": settings()},
    {"label": "R84c_VWAP_termstruct_PV6", "expression": R84c, "settings": settings()},
    {"label": "R84d_trade_when_PV6",      "expression": R84d, "settings": settings()},
    {"label": "R84e_VWAPmom_x_relvol_PV6","expression": R84e, "settings": settings()},
    {"label": "R84f_VWAPmom60_PV6_IND",   "expression": R84f, "settings": settings(neutralization="INDUSTRY")},
    {"label": "R84g_argmax_VWAP_rev_PV6", "expression": R84g, "settings": settings()},
    {"label": "R84h_multiwin_PV6",        "expression": R84h, "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r84_long_windows_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R84: longer VWAP windows + term-structure + trade_when + composites.\n"
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
    md = "# R84 long windows + composites\n\n"
    md += ("| variant | neut | SH | TO | FIT | checks | conc | sub | sc | gate |\n"
           "|---|---|---:|---:|---:|---|---|---|---|---|\n")
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
        s_ = r['settings']
        md += (f"| {r['variant']} | {s_['neutralization']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {sc.get('value','-')} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | - | FAIL | - | - | - | - | - | - | no |  "
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
