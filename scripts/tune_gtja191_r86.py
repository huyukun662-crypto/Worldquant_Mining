"""Round 86: stack two-ceiling winners + decay/neut sweeps on MA60.

Two structurally distinct alphas both produce SH=1.00 conc-PASS:
  R81b -- VWAPmom60_PV6 + SUBIND  (intermediate-term VWAP momentum)
  R85b -- MA60 reversion + PV6    (classical mean reversion)

If their signals are not perfectly correlated, additive composite
could break the 1.00 ceiling.

R86a  add(MA60_PV6, VWAPmom60_PV6)                 dual stack
R86b  add 3-way: + VWAP rankcorr base               triple stack
R86c  MA60 reversion + decay=15                      faster decay
R86d  MA60 reversion + decay=50                      slower decay
R86e  MA60 reversion + INDUSTRY                      diff neut
R86f  MA90 reversion + PV6                           longer base window
R86g  rank(close/MA60 rev) instead of PV6           rank-transform
R86h  zscore(close/MA60 rev) -- no PV6              pure linear

Gate: SH>=1.5, TO<0.20, conc+sub PASS. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r86")
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


MA60_rev = "reverse(divide(close, ts_mean(close, 60)))"
MA60_PV6 = f"signed_power(zscore({MA60_rev}), 2)"
VWAPmom60_PV6 = f"signed_power(zscore(reverse({vwret(60)})), 2)"
VWAP_rankcorr_PV6 = f"signed_power(zscore(reverse(ts_corr(rank(vwap), rank(volume), 30))), 2)"

R86a = W(f"add({MA60_PV6}, {VWAPmom60_PV6})")
R86b = W(f"add(add({MA60_PV6}, {VWAPmom60_PV6}), {VWAP_rankcorr_PV6})")
R86c = W(MA60_PV6, decay=15)
R86d = W(MA60_PV6, decay=50)
R86e = W(MA60_PV6, decay=30)  # neut=INDUSTRY via settings override below
MA90_rev = "reverse(divide(close, ts_mean(close, 90)))"
MA90_PV6 = f"signed_power(zscore({MA90_rev}), 2)"
R86f = W(MA90_PV6)
R86g = W(f"rank({MA60_rev})")
R86h = W(f"zscore({MA60_rev})")

VARIANTS = [
    {"label": "R86a_MA60_plus_VWAPmom60",   "expression": R86a, "settings": settings()},
    {"label": "R86b_triple_stack",          "expression": R86b, "settings": settings()},
    {"label": "R86c_MA60_PV6_decay15",      "expression": R86c, "settings": settings()},
    {"label": "R86d_MA60_PV6_decay50",      "expression": R86d, "settings": settings()},
    {"label": "R86e_MA60_PV6_IND",          "expression": R86e, "settings": settings(neutralization="INDUSTRY")},
    {"label": "R86f_MA90_PV6",              "expression": R86f, "settings": settings()},
    {"label": "R86g_MA60_rev_rank",         "expression": R86g, "settings": settings()},
    {"label": "R86h_MA60_rev_zscore_only",  "expression": R86h, "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r86_stack_winners_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R86: stack the two SH=1.00 ceiling winners (MA60_rev + VWAPmom60) "
        "in different ways to break the 1.00 conc-PASS wall.\n"
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
    md = "# R86 stack winners\n\n"
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
