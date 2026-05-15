"""Round 80: no-close/open fix-loop on R77c G62 + new amp envelopes.

After R77-R79, the best no-close/open base remains R77c G62
(-corr(high, rank(volume), 5)) at raw SH +0.88. PV6 doesn't lift it
(rank-corr already bounded). Need a DIFFERENT amplification.

Strategies tried below:

  R80a  G62 in FF5-vwap envelope (rank smoothed x reverse-VWAP-z x logvol)
  R80b  range_TS in FF5-vwap envelope
  R80c  G62 + INDUSTRY neutralization
  R80d  G62 with longer corr window (20 instead of 5)
  R80e  G62 short-long corr difference (5d - 20d)
  R80f  VWAP 20d momentum + PV6
  R80g  G62 with ts_zscore 60 input bound
  R80h  corr ratio: corr(H,V) / (abs(corr(L,V)) + 1) -- composite

Settings: USA TOP3000 delay=1 decay=8 trunc=0.08 SUBINDUSTRY pasteur ON.
Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7.
DO NOT auto-submit -- verify manually first.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r80")
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


# Bases / building blocks
G62 = "multiply(-1, ts_corr(high, rank(volume), 5))"
G62_LONG = "multiply(-1, ts_corr(high, rank(volume), 20))"
HL = "subtract(high, low)"
RTS = f"reverse(divide(ts_mean({HL}, 5), ts_mean({HL}, 60)))"
VWAP_REV_Z = "reverse(ts_zscore(vwap, 6))"
VOLWT = "log(divide(volume, adv20))"
VWAP_RET20 = "divide(subtract(vwap, ts_delay(vwap, 20)), ts_delay(vwap, 20))"
G62_5 = G62
G62_20 = "multiply(-1, ts_corr(high, rank(volume), 20))"


def ff5_vwap(src: str) -> str:
    return W(
        f"multiply(multiply(rank(ts_mean({src}, 20)), {VWAP_REV_Z}), {VOLWT})",
        decay=30,
    )


R80a = ff5_vwap(G62)
R80b = ff5_vwap(RTS)
R80c = W(G62)  # different neutralization handled in settings
R80d = W(G62_LONG)
R80e = W(f"subtract({G62_5}, {G62_20})")
R80f = W(f"signed_power(zscore(reverse({VWAP_RET20})), 2)")  # PV6 on VWAP 20d mom rev
R80g = W(f"ts_zscore({G62}, 60)")
R80h = W(
    f"divide(ts_corr(high, volume, 10), "
    f"add(abs(ts_corr(low, volume, 10)), 0.001))"
)


VARIANTS = [
    {"label": "R80a_G62_FF5vwap",       "expression": R80a, "settings": settings()},
    {"label": "R80b_rangeTS_FF5vwap",   "expression": R80b, "settings": settings()},
    {"label": "R80c_G62_INDUSTRY",      "expression": R80c, "settings": settings(neutralization="INDUSTRY")},
    {"label": "R80d_G62_corr20",        "expression": R80d, "settings": settings()},
    {"label": "R80e_G62_corr5minus20",  "expression": R80e, "settings": settings()},
    {"label": "R80f_VWAPmom20_PV6",     "expression": R80f, "settings": settings()},
    {"label": "R80g_G62_tszscore60",    "expression": R80g, "settings": settings()},
    {"label": "R80h_corr_HV_over_LV",   "expression": R80h, "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r80_g62_fixloop_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R80: fix-loop on R77c G62 best no-close/open base via "
        "alternate amp envelopes (FF5-vwap, INDUSTRY, ts_zscore-IN, "
        "multi-window corr diff).\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        log.info(f"      neut={v['settings']['neutralization']}")
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
    md = "# R80 G62 fix-loop\n\n"
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
                   f"settings: {json.dumps({k:v for k,v in r['settings'].items() if k in ('universe','truncation','neutralization')})}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
