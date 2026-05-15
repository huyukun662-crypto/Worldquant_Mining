"""Round 69: clear the conc 0.10 cliff -- SSS and PPP are 0.003-0.004 over.

R68 results, sorted by conc gap to the 0.10 limit:
  SSS pow 1.5 + trunc 0.03    SH +1.66  conc 0.103  +0.003 over
  PPP pow 1.2                 SH +1.52  conc 0.104  +0.004 over
  QQQ pow 1.3                 SH +1.60  conc 0.126
  OOO zscoreIN_pow2           SH +1.83  conc 0.143
  RRR pow 1.4                 SH +1.67  conc 0.153
  TTT pow 1.5 + INDUSTRY      SH +1.72  conc 0.170
  HHH pow 2  + trunc 0.03     SH +1.90  conc 0.334  (R67)
  UUU ts_zscoreIN_pow2        SH -0.28  conc PASS (sign-flipped, useless)

Two paths are within 0.005 of clearing conc. This round stacks the
remaining constraints:

  PV1  PPP (pow 1.2) + trunc 0.05            tighter truncation
  PV2  PPP (pow 1.2) + trunc 0.03            tighter still
  PV3  PPP (pow 1.2) + INDUSTRY              broader neutralization bucket
  PV4  SSS (pow 1.5) + trunc 0.02            shave more
  PV5  SSS (pow 1.5) + INDUSTRY              alt bucket
  PV6  OOO (zscoreIN pow 2) + trunc 0.03     bound + cap
  PV7  OOO (zscoreIN pow 2) + trunc 0.02     bound + tight cap
  PV8  BB pow 1.1                            tiny amp baseline

Gate: SH >= 1.5 ^ TO < 0.20 ^ conc + sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r69")
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
REV_BB = f"reverse({BB20})"

PPP = W(f"signed_power({REV_BB}, 1.2)")
SSS = W(f"signed_power({REV_BB}, 1.5)")
OOO = W(f"signed_power(zscore({REV_BB}), 2)")
P11 = W(f"signed_power({REV_BB}, 1.1)")

VARIANTS = [
    {"label": "PV1_PPP_trunc0.05",  "expression": PPP,
     "settings": settings(truncation=0.05)},
    {"label": "PV2_PPP_trunc0.03",  "expression": PPP,
     "settings": settings(truncation=0.03)},
    {"label": "PV3_PPP_industry",   "expression": PPP,
     "settings": settings(neutralization="INDUSTRY")},
    {"label": "PV4_SSS_trunc0.02",  "expression": SSS,
     "settings": settings(truncation=0.02)},
    {"label": "PV5_SSS_industry",   "expression": SSS,
     "settings": settings(neutralization="INDUSTRY")},
    {"label": "PV6_OOO_trunc0.03",  "expression": OOO,
     "settings": settings(truncation=0.03)},
    {"label": "PV7_OOO_trunc0.02",  "expression": OOO,
     "settings": settings(truncation=0.02)},
    {"label": "PV8_BB_pow1.1",      "expression": P11,
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r69_clear_conc_cliff_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R69: tighten truncation/neutralization on PPP/SSS/OOO -- the three "
        "BB-amp variants closest to conc PASS (within 0.005 of the 0.10 limit).\n"
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
    md = "# R69 clear concentration cliff\n\n"
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
