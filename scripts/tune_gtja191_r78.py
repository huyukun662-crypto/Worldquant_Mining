"""Round 78: PV6 / amp sweep on R77's clean-passing pure-PV bases.

R77 found 4 bases that PASS conc + sub but SH only 0.61-0.88:
  R77c alpha_62  -corr(H, rank(V), 5)            SH +0.88
  R77d alpha_90  -rank(corr(rank(VWAP), rank(V), 5)) SH +0.81
  R77f alpha_141 -rank(corr(rank(H), rank(mean(V,15)), 9)) SH +0.77
  R77h range_TS  (5d range)/(60d range) reversed SH +0.61

Historical lift from PV6 recipe (zscore-IN + signed_power(., 2)):
~+0.7 SH on suitable bases. Applied here, the projection is:
  R77c -> 1.58 (possible pass!)
  R77d -> 1.51 (borderline)
  R77f -> 1.47 (just below)
  R77h -> 1.31

R78 variants (8 total) -- amp sweep on the strongest two bases (G62, G90)
plus PV6 on the weaker bases:

  R78a  G62 PV6 (zscore-IN + pow 2)
  R78b  G90 PV6
  R78c  G141 PV6
  R78d  range_TS PV6
  R78e  G62 pow 1.5 (gentler if PV6 conc-fails)
  R78f  G62 PV6 + trunc 0.03 (stack constraints)
  R78g  G62 zscore-IN + pow 3 (stronger amp)
  R78h  G62 + log-volume modulation + decay 30

Settings: USA TOP3000 delay 1 decay 8 (default) SUBINDUSTRY pasteur ON.
Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7 vs
A1nnxAdw + 9q9o0zme (both ACTIVE).
DO NOT auto-submit -- only print results; submission decided separately
after manual verification.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r78")
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


# Bases from R77 (raw expressions, NOT pre-wrapped with W)
G62  = f"multiply(-1, ts_corr(high, rank(volume), 5))"
G90  = f"multiply(-1, rank(ts_corr(rank(vwap), rank(volume), 5)))"
G141 = f"multiply(-1, rank(ts_corr(rank(high), rank(ts_mean(volume, 15)), 9)))"
HL = "subtract(high, low)"
RTS  = f"reverse(divide(ts_mean({HL}, 5), ts_mean({HL}, 60)))"
VOLWT = "log(divide(volume, adv20))"


def pv6(base: str) -> str:
    return W(f"signed_power(zscore({base}), 2)")


VARIANTS = [
    {"label": "R78a_G62_PV6",            "expression": pv6(G62),   "settings": settings()},
    {"label": "R78b_G90_PV6",            "expression": pv6(G90),   "settings": settings()},
    {"label": "R78c_G141_PV6",           "expression": pv6(G141),  "settings": settings()},
    {"label": "R78d_rangeTS_PV6",        "expression": pv6(RTS),   "settings": settings()},
    {"label": "R78e_G62_pow15",          "expression": W(f"signed_power({G62}, 1.5)"),
     "settings": settings()},
    {"label": "R78f_G62_PV6_trunc0.03",  "expression": pv6(G62),   "settings": settings(truncation=0.03)},
    {"label": "R78g_G62_zIN_pow3",       "expression": W(f"signed_power(zscore({G62}), 3)"),
     "settings": settings()},
    {"label": "R78h_G62_x_logvol",       "expression": W(f"multiply({G62}, {VOLWT})"),
     "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r78_purePV_amp_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R78: PV6 / amp sweep on R77's clean-passing pure-PV bases. "
        "DO NOT auto-submit.\n"
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
    md = "# R78 pure-PV amplification sweep\n\n"
    md += ("| variant | trunc | neut | SH | TO | FIT | checks | conc | sub | sc_v | gate |\n"
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
