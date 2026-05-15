"""Round 74: apply the FF5 (news-impact winner) composite recipe to GTJA bases.

R73 highlight: CC5 GTJA158 + PV6 recipe -> SH +1.30 / TO 0.086 (just
under the 1.5 gate). PV6 lifts ~+0.7 SH over raw base but the bases
are too weak (SH 0.50-0.59 raw).

FF5 (R61 news winner) used a 3-way composite:
  zscore(ts_decay_linear(multiply(multiply(
      rank(ts_mean(<source>, 20)),
      reverse(ts_zscore(returns, 6))),
      log(add(divide(volume, adv20), 1))), 30))
This hit SH +1.59 on mean_news_impact_projection. The reverse-momentum
+ log-volume modulation is a different amplification than PV6.

R74 applies this to 5 GTJA bases plus 3 alt amplifications:

  DD1  GTJA158 in FF5 envelope
  DD2  GTJA063 (RSI inverted) in FF5 envelope
  DD3  GTJA133 (day balance) in FF5 envelope
  DD4  GTJA070 (dollar-vol-vol) in FF5 envelope
  DD5  GTJA106 (raw mom 20) in FF5 envelope
  DD6  GTJA158 signed_power(., 3) -- cube amp (vs PV6's pow 2)
  DD7  CC5 with decay 60 (longer smoothing)
  DD8  GTJA158 x reverse(ts_zscore(returns, 6)) -- partial FF5

Gate: SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7 vs A1nnxAdw.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r74")
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
# Raw (non-reversed) bases for FF5 envelope
G158_RAW = f"divide(subtract(subtract(high, {MA15}), subtract(low, {MA15})), close)"
G063_RAW = f"divide(ts_decay_linear({UP}, 6), ts_decay_linear(abs({DC}), 6))"
G133_RAW = f"subtract(ts_arg_max(high, 20), ts_arg_min(low, 20))"
G070_RAW = f"ts_std_dev(multiply(close, volume), 6)"
G106_RAW = f"subtract(close, ts_delay(close, 20))"

REV_MOM6 = "reverse(ts_zscore(returns, 6))"
VOLWT = "log(add(divide(volume, adv20), 1))"


def ff5(src_raw: str) -> str:
    """FF5 envelope on a raw source: rank(ts_mean(src,20)) * rev_mom * log_vol."""
    return W(
        f"multiply(multiply(rank(ts_mean({src_raw}, 20)), {REV_MOM6}), {VOLWT})",
        decay=30,
    )


# Reversed bases (where direction needs flip for natural mean-revert)
G158_REV = f"reverse({G158_RAW})"
G063_REV = f"reverse({G063_RAW})"


DD1 = ff5(G158_REV)
DD2 = ff5(G063_REV)
DD3 = ff5(G133_RAW)
DD4 = ff5(f"reverse({G070_RAW})")  # rv reversed for direction
DD5 = ff5(f"reverse({G106_RAW})")  # mom reversed
DD6 = W(f"signed_power({G158_REV}, 3)")
DD7 = W(f"signed_power(zscore({G158_REV}), 2)", decay=60)
DD8 = W(f"multiply({G158_REV}, {REV_MOM6})")


VARIANTS = [
    {"label": "DD1_G158_FF5",           "expression": DD1},
    {"label": "DD2_G063_FF5",           "expression": DD2},
    {"label": "DD3_G133_FF5",           "expression": DD3},
    {"label": "DD4_G070_FF5",           "expression": DD4},
    {"label": "DD5_G106_FF5",           "expression": DD5},
    {"label": "DD6_G158_pow3",          "expression": DD6},
    {"label": "DD7_G158_PV6_D60",       "expression": DD7},
    {"label": "DD8_G158_x_revmom",      "expression": DD8},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r74_gtja191_ff5envelope_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R74: apply FF5 (R61 news winner) composite envelope to GTJA bases.\n"
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
    md = "# R74 GTJA191 FF5 envelope\n\n"
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
