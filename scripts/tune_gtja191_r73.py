"""Round 73: GTJA191 composites + apply R69 winning recipe to strongest bases.

R70-R72 lesson: single-source GTJA191 signals all weak on TOP3000.
The historical wins all share two features: composite signals
(multiplicative combo of 2+ orthogonal sources) and amplified
inner distribution (zscore-IN + signed_power, the R69 PV6 recipe).

R72 best bases: GTJA158 (H-L to MA, SH 0.57), GTJA063 (RSI, SH 0.55),
GTJA133 (H/L day balance, SH 0.50), GTJA106 (raw 20d mom, SH 0.59).

This round combines them and applies PV6 amplification:

  CC1  GTJA158 x GTJA063 (both reversed)               multiplicative
  CC2  GTJA158 x GTJA133                               multiplicative
  CC3  GTJA158 x GTJA106                               multiplicative
  CC4  GTJA063 x GTJA106                               multiplicative
  CC5  GTJA158 + PV6 recipe (zscore-IN + pow 2)         amplification
  CC6  GTJA158 acceleration (ts_delta reversed)         acceleration
  CC7  GTJA133 ts_zscore 60                             time-normalized
  CC8  GTJA158 x log relative volume                    vol-weighted

Settings: TOP3000, delay=1, decay=8, trunc=0.08, SUBINDUSTRY, pasteur ON.
Gate: SH >= 1.5 ^ TO < 0.20 ^ ALL 8 WQ checks PASS ^ self_corr<0.7 vs A1nnxAdw.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r73")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def settings() -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": 0.08,
        "neutralization": "SUBINDUSTRY", "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


DC = "subtract(close, ts_delay(close, 1))"
MA15 = "ts_decay_linear(close, 15)"
UP = f"multiply(greater({DC}, 0), {DC})"
# Bases (reversed where applicable for direction-natural mean-revert)
G158 = f"reverse(divide(subtract(subtract(high, {MA15}), subtract(low, {MA15})), close))"
G063 = f"reverse(divide(ts_decay_linear({UP}, 6), ts_decay_linear(abs({DC}), 6)))"
G133 = f"subtract(ts_arg_max(high, 20), ts_arg_min(low, 20))"
G106 = f"reverse(subtract(close, ts_delay(close, 20)))"
VOLWT = "log(divide(volume, adv20))"

CC1 = W(f"multiply({G158}, {G063})")
CC2 = W(f"multiply({G158}, {G133})")
CC3 = W(f"multiply({G158}, {G106})")
CC4 = W(f"multiply({G063}, {G106})")
CC5 = W(f"signed_power(zscore({G158}), 2)")
CC6 = W(f"reverse(ts_delta({G158}, 20))")
CC7 = W(f"ts_zscore({G133}, 60)")
CC8 = W(f"multiply({G158}, {VOLWT})")

VARIANTS = [
    {"label": "CC1_G158xG063",      "expression": CC1},
    {"label": "CC2_G158xG133",      "expression": CC2},
    {"label": "CC3_G158xG106",      "expression": CC3},
    {"label": "CC4_G063xG106",      "expression": CC4},
    {"label": "CC5_G158_PV6recipe", "expression": CC5},
    {"label": "CC6_G158_accel",     "expression": CC6},
    {"label": "CC7_G133_tszscore60","expression": CC7},
    {"label": "CC8_G158_x_logvol",  "expression": CC8},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r73_gtja191_composites_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R73: combine strongest GTJA191 bases multiplicatively + apply "
        "R69 PV6 winning recipe.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        try:
            res = r5.submit(cm.session, v["expression"], settings())
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"], **res}
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
    md = "# R73 GTJA191 composites\n\n"
    md += ("| variant | SH | TO | FIT | checks | conc | sub | gate |\n"
           "|---|---:|---:|---:|---|---|---|---|\n")
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
        md += (f"| {r['variant']} | {r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | no |  "
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
