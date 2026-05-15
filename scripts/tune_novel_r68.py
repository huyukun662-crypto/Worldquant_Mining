"""Round 68: kill the concentration tail without killing SH.

R67 results:
  HHH CCC + trunc 0.03    SH +1.90  FIT +5.09  conc FAIL 0.334
  III CCC + trunc 0.02    SH +1.88  FIT +4.76  conc FAIL 0.303
  GGG CCC + trunc 0.05    SH +1.80  FIT +5.09  conc FAIL 0.368
  KKK BB pow 1.5          SH +1.72  FIT +4.20  conc FAIL 0.186 (closest!)
  LLL CCC + INDUSTRY      SH +1.74  conc 0.385
  MMM CCC + SECTOR        SH +1.73  conc 0.377
  NNN CCC + TOP1000       SH +0.81  (smaller universe collapses signal)
  JJJ rank(BB) pow 2      SH +0.01  (rank-bound destroys variance amp)

Truncation alone can't fix conc -- signed_power(.,2) on raw BB produces
unbounded heavy tails (some names have huge range vol some days, the
square magnifies them, no truncation cap on the input).

Strategy: bound the INPUT distribution before squaring.

  OOO  signed_power(zscore(reverse(BB)), 2)        cross-section zscore in
  PPP  BB pow 1.2                                  very gentle
  QQQ  BB pow 1.3                                  gentle
  RRR  BB pow 1.4                                  middle
  SSS  KKK (pow 1.5) + trunc 0.03                  amp + tight cap
  TTT  KKK (pow 1.5) + INDUSTRY                    amp + broader bucket
  UUU  signed_power(ts_zscore(reverse(BB), 60), 2) time-series zscore in
  VVV  CCC + INDUSTRY + trunc 0.03                 stack constraints

Gate: SH >= 1.5 ^ TO < 0.20 ^ conc + sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r68")
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

OOO = W(f"signed_power(zscore({REV_BB}), 2)")
PPP = W(f"signed_power({REV_BB}, 1.2)")
QQQ = W(f"signed_power({REV_BB}, 1.3)")
RRR = W(f"signed_power({REV_BB}, 1.4)")
KKK = W(f"signed_power({REV_BB}, 1.5)")  # base for SSS / TTT
CCC = W(f"signed_power({REV_BB}, 2)")    # base for VVV
UUU = W(f"signed_power(ts_zscore({REV_BB}, 60), 2)")

VARIANTS = [
    {"label": "OOO_zscoreIN_pow2", "expression": OOO,
     "settings": settings()},
    {"label": "PPP_BB_pow1.2", "expression": PPP,
     "settings": settings()},
    {"label": "QQQ_BB_pow1.3", "expression": QQQ,
     "settings": settings()},
    {"label": "RRR_BB_pow1.4", "expression": RRR,
     "settings": settings()},
    {"label": "SSS_KKK_trunc0.03", "expression": KKK,
     "settings": settings(truncation=0.03)},
    {"label": "TTT_KKK_industry", "expression": KKK,
     "settings": settings(neutralization="INDUSTRY")},
    {"label": "UUU_tszscoreIN_pow2", "expression": UUU,
     "settings": settings()},
    {"label": "VVV_CCC_industry_trunc0.03", "expression": CCC,
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r68_bound_input_pow_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R68: bound input before amplification (cross-section / time-series "
        "zscore) and gentler power 1.2-1.4 to break the conc-vs-SH lock.\n"
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
    md = "# R68 bound input + gentler power\n\n"
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
