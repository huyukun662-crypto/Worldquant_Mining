"""Round 81: R80f VWAP-mom20 + PV6 fix-loop -- 0.98 SH, need 1.5.

R80f = zscore(ts_decay_linear(signed_power(zscore(reverse(
       (vwap - vwap[20]) / vwap[20])), 2), 30))
SH +0.98 / TO 0.102 / FIT +1.45 / conc + sub PASS / 6/8 (LOW_SHARPE fails).

Need +0.52 SH to clear 1.5. Strategies:

  R81a  cube amp (signed_power(., 3) + zscore-IN)         stronger
  R81b  PV6 + INDUSTRY                                    alt bucket
  R81c  PV6 + trunc 0.03                                  tighter cap
  R81d  FF5-vwap envelope (rank x rev-VWAP-z x logvol)    different env
  R81e  VWAPmom20 x range_TS composite (both weak/clean)
  R81f  pow 2.5 between PV6 and cube
  R81g  decay 60                                          longer smoothing
  R81h  VWAPmom30 + PV6                                   longer mom window

Settings: USA TOP3000 delay 1 decay 8 trunc 0.08 (overrides as noted)
SUBINDUSTRY pasteur ON.
Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7.
DO NOT auto-submit -- verify manually first.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r81")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings(truncation: float = 0.08,
             neutralization: str = "SUBINDUSTRY") -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": truncation,
        "neutralization": neutralization, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


VWAP_RET20 = "divide(subtract(vwap, ts_delay(vwap, 20)), ts_delay(vwap, 20))"
VWAP_RET30 = "divide(subtract(vwap, ts_delay(vwap, 30)), ts_delay(vwap, 30))"
VWAP_REV_Z = "reverse(ts_zscore(vwap, 6))"
VOLWT = "log(divide(volume, adv20))"
HL = "subtract(high, low)"
RTS = f"reverse(divide(ts_mean({HL}, 5), ts_mean({HL}, 60)))"

# Base reverse VWAP mom
BASE = f"reverse({VWAP_RET20})"

R81a = W(f"signed_power(zscore({BASE}), 3)")                 # cube + zscore-IN
R81b = W(f"signed_power(zscore({BASE}), 2)")                 # PV6 + INDUSTRY (via settings)
R81c = W(f"signed_power(zscore({BASE}), 2)")                 # PV6 + trunc 0.03
R81d = W(f"multiply(multiply(rank(ts_mean({BASE}, 20)), {VWAP_REV_Z}), {VOLWT})")
R81e = W(f"signed_power(zscore(multiply({BASE}, {RTS})), 2)")
R81f = W(f"signed_power(zscore({BASE}), 2.5)")
R81g = W(f"signed_power(zscore({BASE}), 2)", decay=60)
R81h = W(f"signed_power(zscore(reverse({VWAP_RET30})), 2)")


VARIANTS = [
    {"label": "R81a_VWAPmom_zIN_pow3",   "expression": R81a, "settings": settings()},
    {"label": "R81b_VWAPmom_PV6_IND",    "expression": R81b, "settings": settings(neutralization="INDUSTRY")},
    {"label": "R81c_VWAPmom_PV6_tr03",   "expression": R81c, "settings": settings(truncation=0.03)},
    {"label": "R81d_VWAPmom_FF5",        "expression": R81d, "settings": settings()},
    {"label": "R81e_VWAPmom_x_rangeTS",  "expression": R81e, "settings": settings()},
    {"label": "R81f_VWAPmom_pow25",      "expression": R81f, "settings": settings()},
    {"label": "R81g_VWAPmom_PV6_D60",    "expression": R81g, "settings": settings()},
    {"label": "R81h_VWAPmom30_PV6",      "expression": R81h, "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r81_vwapmom_fixloop_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R81: fix-loop on R80f VWAP 20d mom + PV6 (SH 0.98 -> need 1.5).\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        log.info(f"      trunc={v['settings']['truncation']} neut={v['settings']['neutralization']}")
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
    md = "# R81 VWAP-mom fix-loop\n\n"
    md += ("| variant | trunc | neut | SH | TO | FIT | checks | conc | sub | sc | gate |\n"
           "|---|---:|---|---:|---:|---:|---|---|---|---|---|\n")
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
        md += (f"| {r['variant']} | {s_['truncation']} | {s_['neutralization']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {sc.get('value','-')} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | - | - | FAIL | - | - | - | - | - | - | no |  "
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
