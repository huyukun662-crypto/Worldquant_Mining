"""Round 75: kill GTJA158 cube's concentration problem (analog of R67-R69).

R74 highlight:
  DD6  GTJA158 signed_power 3  SH +2.09  TO 0.117  FIT +6.12
       CONCENTRATED_WEIGHT FAIL 0.459 (limit 0.10)

Exact mirror of R66 CCC (BB pow 2 SH 1.68 conc 0.40). The fix that
worked for CCC -> A1nnxAdw (SH 1.86, 8/8 PASS):
  1. zscore the INPUT before power     (bounds the distribution)
  2. tighten truncation to 0.03         (caps per-name weight)
  3. SUBINDUSTRY neutralization stays
That recipe = "PV6" in our nomenclature.

This round applies the PV6 playbook to GTJA158 cube + adjacent
options.

  EE1  zscore(G158_rev) -> signed_power(., 3)        PV6 analog with pow 3
  EE2  G158 pow 3 + trunc 0.03                       baseline trunc fix
  EE3  G158 pow 3 + trunc 0.02                       tighter
  EE4  G158 pow 3 + INDUSTRY                         broader bucket
  EE5  EE1 + trunc 0.03                              full stack
  EE6  rank(G158_rev) -> signed_power(., 3)          rank-bound input
  EE7  G158 signed_power 2.5                         between PV6 and cube
  EE8  G158 pow 2.5 + trunc 0.03                     2.5 + tight cap

Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7 vs A1nnxAdw.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r75")
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


MA15 = "ts_decay_linear(close, 15)"
G158_RAW = f"divide(subtract(subtract(high, {MA15}), subtract(low, {MA15})), close)"
G158_REV = f"reverse({G158_RAW})"

EE1 = W(f"signed_power(zscore({G158_REV}), 3)")
EE2 = W(f"signed_power({G158_REV}, 3)")  # base for trunc variations
EE3 = EE2
EE4 = EE2
EE5 = EE1  # PV6 analog stacked with trunc 0.03
EE6 = W(f"signed_power(rank({G158_REV}), 3)")
EE7 = W(f"signed_power({G158_REV}, 2.5)")
EE8 = EE7  # for trunc 0.03

VARIANTS = [
    {"label": "EE1_G158_zIN_pow3",        "expression": EE1,
     "settings": settings()},
    {"label": "EE2_G158_pow3_trunc0.03",  "expression": EE2,
     "settings": settings(truncation=0.03)},
    {"label": "EE3_G158_pow3_trunc0.02",  "expression": EE2,
     "settings": settings(truncation=0.02)},
    {"label": "EE4_G158_pow3_INDUSTRY",   "expression": EE2,
     "settings": settings(neutralization="INDUSTRY")},
    {"label": "EE5_zIN_pow3_trunc0.03",   "expression": EE1,
     "settings": settings(truncation=0.03)},
    {"label": "EE6_rank_pow3",            "expression": EE6,
     "settings": settings()},
    {"label": "EE7_G158_pow25",           "expression": EE7,
     "settings": settings()},
    {"label": "EE8_G158_pow25_trunc0.03", "expression": EE7,
     "settings": settings(truncation=0.03)},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r75_g158_cube_fix_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R75: kill GTJA158 cube concentration via PV6-style zscore-IN, "
        "truncation, neutralization. Mirror of R67-R69 BB fix.\n"
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
    md = "# R75 GTJA158 cube concentration fix\n\n"
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
