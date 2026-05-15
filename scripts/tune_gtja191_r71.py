"""Round 71: amplify GTJA002 -- the R70 lead (SH +1.74 but TO 0.70).

R70 results:
  GTJA002 reverse(ts_delta(price_position, 1))  SH +1.74  TO 0.699  FIT +0.65
    -- strong reversal signal but daily-Delta -> daily turnover.
  All other 7 candidates SH <= 0.54 (most negative or near zero).

R71 strategy: keep GTJA002's mean-reversion edge, kill the turnover.
8 variants slow the signal via decay, pre-smoothing, longer Delta
window, BB-style amplification (zscore-IN + signed_power from R69 PV6):

  AA1  decay 30                                  baseline slowdown
  AA2  decay 60                                  heavier
  AA3  smooth input ts_mean(pos, 5) -> delta     averaging the source
  AA4  smooth input ts_mean(pos, 10) -> delta    longer smoothing
  AA5  delta(., 5) -> decay 30                   longer delta window
  AA6  signed_power(., 1.5) + decay 30           gentle tail amp
  AA7  zscore-IN + signed_power(., 2) + decay 30 PV6 recipe
  AA8  smooth5 + signed_power(., 1.5) + decay 30 combine smoothing+amp

Settings: TOP3000, delay=1, decay=8 unless overridden, trunc 0.08,
SUBINDUSTRY, pasteurization ON.
Gate: SH >= 1.5 ^ TO < 0.20 ^ ALL 8 WQ checks PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r71")
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


POS = "divide(subtract(subtract(close, low), subtract(high, close)), subtract(high, low))"

# AA1 baseline slowdown
AA1 = W(f"reverse(ts_delta({POS}, 1))", decay=30)
# AA2 heavier decay
AA2 = W(f"reverse(ts_delta({POS}, 1))", decay=60)
# AA3 smooth source 5d then delta
AA3 = W(f"reverse(ts_delta(ts_mean({POS}, 5), 1))", decay=30)
# AA4 smooth source 10d
AA4 = W(f"reverse(ts_delta(ts_mean({POS}, 10), 1))", decay=30)
# AA5 longer delta window
AA5 = W(f"reverse(ts_delta({POS}, 5))", decay=30)
# AA6 gentle amp on raw
AA6 = W(f"signed_power(reverse(ts_delta({POS}, 1)), 1.5)", decay=30)
# AA7 PV6 recipe (zscore-IN + pow2)
AA7 = W(f"signed_power(zscore(reverse(ts_delta({POS}, 1))), 2)", decay=30)
# AA8 smooth5 + amp
AA8 = W(f"signed_power(reverse(ts_delta(ts_mean({POS}, 5), 1)), 1.5)", decay=30)


VARIANTS = [
    {"label": "AA1_GTJA002_D30",        "expression": AA1},
    {"label": "AA2_GTJA002_D60",        "expression": AA2},
    {"label": "AA3_GTJA002_smooth5",    "expression": AA3},
    {"label": "AA4_GTJA002_smooth10",   "expression": AA4},
    {"label": "AA5_GTJA002_delta5_D30", "expression": AA5},
    {"label": "AA6_GTJA002_pow15_D30",  "expression": AA6},
    {"label": "AA7_GTJA002_PV6_recipe", "expression": AA7},
    {"label": "AA8_GTJA002_sm5_pow15",  "expression": AA8},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r71_gtja002_amplify_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R71: amplify GTJA002 (SH +1.74 / TO 0.70 in R70). Slow via "
        "decay, pre-smoothing, longer delta, amplification.\n"
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
    md = "# R71 GTJA002 amplification\n\n"
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
