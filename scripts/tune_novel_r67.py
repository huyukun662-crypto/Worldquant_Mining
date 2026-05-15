"""Round 67: fix CCC's concentration problem -- the 1.68 SH stretched
the BB plateau but one name hit 40% weight on 2019-02-04.

R66 highlight:
  CCC = zscore(ts_decay_linear(signed_power(reverse(BB20), 2), 30))
        SH +1.68  TO 0.094  FIT +4.97  SUB_SH 0.99  6/8 PASS
        FAILS CONCENTRATED_WEIGHT at 0.398 (limit 0.10)

Strategy: keep the amplification recipe, constrain concentration via
truncation, rank-bounded input, alternative power, neutralization,
and universe.

  GGG  CCC + trunc 0.05         (cap weight)
  HHH  CCC + trunc 0.03
  III  CCC + trunc 0.02
  JJJ  rank(BB) -> signed_power(.,2)   (bounded input)
  KKK  signed_power(BB, 1.5)          (gentler tail amp)
  LLL  CCC + INDUSTRY neutralization
  MMM  CCC + SECTOR neutralization
  NNN  CCC + TOP1000 universe

Gate: SH >= 1.5 ^ TO < 0.20 ^ conc + sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r67")
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


RS = "signed_power(log(divide(high, low)), 2)"
BB20 = f"ts_mean({RS}, 20)"

# CCC base (1.68 SH but conc fail)
CCC = W(f"signed_power(reverse({BB20}), 2)")
# JJJ rank-bounded amplification
JJJ = W(f"signed_power(rank(reverse({BB20})), 2)")
# KKK gentler power 1.5
KKK = W(f"signed_power(reverse({BB20}), 1.5)")

VARIANTS = [
    {"label": "GGG_CCC_trunc0.05", "expression": CCC,
     "settings": settings(truncation=0.05)},
    {"label": "HHH_CCC_trunc0.03", "expression": CCC,
     "settings": settings(truncation=0.03)},
    {"label": "III_CCC_trunc0.02", "expression": CCC,
     "settings": settings(truncation=0.02)},
    {"label": "JJJ_rankBB_pow2", "expression": JJJ,
     "settings": settings()},
    {"label": "KKK_BB_pow1.5", "expression": KKK,
     "settings": settings()},
    {"label": "LLL_CCC_industry", "expression": CCC,
     "settings": settings(neutralization="INDUSTRY")},
    {"label": "MMM_CCC_sector", "expression": CCC,
     "settings": settings(neutralization="SECTOR")},
    {"label": "NNN_CCC_top1000", "expression": CCC,
     "settings": settings(universe="TOP1000")},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r67_ccc_fix_concentration_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R67: CCC hit SH 1.68 / TO 0.094 / FIT 4.97 but FAILS conc (40% "
        "on one name). Fix via truncation, rank-bounded amp, gentler "
        "power 1.5, alternative neutralization, smaller universe.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        log.info(f"      univ={v['settings']['universe']} "
                 f"trunc={v['settings']['truncation']} "
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
                     f"FIT={res['fitness']:+.3f}")
            for chk in res.get("checks", []):
                if chk.get("name") in ("CONCENTRATED_WEIGHT","LOW_SUB_UNIVERSE_SHARPE"):
                    log.info(f"        {chk.get('name')}: {chk.get('result')} value={chk.get('value')}")
        else:
            log.warning(f"      FAIL: {res.get('error', '?')[:160]}")
    md = "# R67 fix CCC concentration\n\n"
    md += ("| variant | univ | trunc | neut | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---|---:|---|---:|---:|---:|---|---|---|\n")
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
        md += (f"| {r['variant']} | {s_['universe']} | {s_['truncation']} | "
               f"{s_['neutralization']} | {r['sharpe']:+.3f} | "
               f"{r['turnover']:.3f} | {r['fitness']:+.3f} | {c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | - | - | - | FAIL | - | - | - | - | no |  "
               f"{r.get('error','?')[:80]}\n")
    md += f"\n**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): {len(survivors)}/{len(results)}**\n"
    if survivors:
        md += "\n## Survivor expressions\n\n"
        for r in survivors:
            md += (f"### {r['variant']} -- alpha {r.get('alpha_id','?')}\n"
                   f"SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
                   f"FIT={r['fitness']:+.3f}\n"
                   f"settings: {json.dumps({k:v for k,v in r['settings'].items() if k in ('universe','truncation','neutralization','decay','delay')})}\n"
                   f"```\n{r['expression']}\n```\n\n")
    (session_dir / "outputs" / "final_summary.md").write_text(md)
    (session_dir / "working" / "results.json").write_text(json.dumps(results, indent=2))
    log.info(f"DONE: {session_dir / 'outputs' / 'final_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
