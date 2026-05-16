"""Round 93: trade_when 3-tier pattern (final cheat-sheet model).

From cheat sheet (BV1LXRMBHEbR):
  trade_when( group( ts_rank( <field> ) ) )
     ^         ^         ^
     3rd      2nd       1st
   open/close cross-sec  signal norm
   trigger    bucket     (time series)

trade_when(open_trigger, x, close_trigger):
  - when open_trigger fires: positions <- x
  - close_trigger=-1: never close, keep position (decay by setting)

Hypothesis: only update when |signal| is strong -> select for high
information moments -> SH lift + TO drop.

  R93a  trade_when(|z|>1.5) + p25 + d=15            gate strong
  R93b  trade_when(|z|>1.0) + p25 + d=15            gate medium
  R93c  trade_when(|z|>2.0) + p25 + d=15            gate very strong
  R93d  trade_when 1.5 + group_neut(p25, subind)     2-tier add
  R93e  trade_when 1.5 + ts_rank inner               full 3-tier
  R93f  trade_when high_vol regime                   regime gate
  R93g  trade_when high_volume                       liquidity gate
  R93h  trade_when 1.5 + group_neut + ts_rank        canonical 3-tier

Gate: SH>=1.25 ^ TO<0.20 ^ conc+sub PASS. DO NOT auto-submit.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r93")
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


def W(core: str, decay: int = 15) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


Z_INNER = "zscore(reverse(divide(close, ts_mean(close, 60))))"
P25_CORE = f"signed_power({Z_INNER}, 2.5)"


def tw(cond: str, x: str) -> str:
    return f"trade_when({cond}, {x}, -1)"


# regime-gate signals
HIGH_VOL = "greater(ts_std_dev(returns, 20), ts_mean(ts_std_dev(returns, 20), 60))"
HIGH_VOLUME = "greater(volume, ts_mean(volume, 20))"

R93a = W(tw(f"greater(abs({Z_INNER}), 1.5)", P25_CORE))
R93b = W(tw(f"greater(abs({Z_INNER}), 1.0)", P25_CORE))
R93c = W(tw(f"greater(abs({Z_INNER}), 2.0)", P25_CORE))
R93d = W(tw(f"greater(abs({Z_INNER}), 1.5)", f"group_neutralize({P25_CORE}, subindustry)"))
R93e_inner = f"signed_power(ts_rank({Z_INNER}, 60), 2.5)"
R93e = W(tw(f"greater(abs({Z_INNER}), 1.5)", R93e_inner))
R93f = W(tw(HIGH_VOL, P25_CORE))
R93g = W(tw(HIGH_VOLUME, P25_CORE))
R93h_inner = f"group_neutralize({R93e_inner}, subindustry)"
R93h = W(tw(f"greater(abs({Z_INNER}), 1.5)", R93h_inner))

VARIANTS = [
    {"label": "R93a_tw_z15_p25",          "expression": R93a, "settings": settings()},
    {"label": "R93b_tw_z10_p25",          "expression": R93b, "settings": settings()},
    {"label": "R93c_tw_z20_p25",          "expression": R93c, "settings": settings()},
    {"label": "R93d_tw_z15_gn_p25",       "expression": R93d, "settings": settings()},
    {"label": "R93e_tw_z15_tsrank_p25",   "expression": R93e, "settings": settings()},
    {"label": "R93f_tw_highvol_p25",      "expression": R93f, "settings": settings()},
    {"label": "R93g_tw_highvolume_p25",   "expression": R93g, "settings": settings()},
    {"label": "R93h_full3tier_canonical", "expression": R93h, "settings": settings()},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r93_trade_when_3tier_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R93: trade_when 3-tier canonical pattern from consultant cheat sheet.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression'][:140]}...")
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
    md = "# R93 trade_when 3-tier\n\n"
    md += ("| variant | SH | TO | FIT | checks | conc | sub | sc | gate |\n"
           "|---|---:|---:|---:|---|---|---|---|---|\n")
    survivors = []
    for r in sorted([r for r in results if r.get('ok')],
                    key=lambda x: x['sharpe'], reverse=True):
        conc = next((c for c in r['checks'] if c['name']=='CONCENTRATED_WEIGHT'), {})
        sub = next((c for c in r['checks'] if c['name']=='LOW_SUB_UNIVERSE_SHARPE'), {})
        sc = next((c for c in r['checks'] if c['name']=='SELF_CORRELATION'), {})
        conc_ok = conc.get('result')=='PASS'
        sub_ok = sub.get('result')=='PASS'
        all_pass = (r['sharpe']>=1.25 and r['turnover']<0.20 and conc_ok and sub_ok)
        if all_pass: survivors.append(r)
        c = "P" if conc_ok else f"F({conc.get('value','?')})"
        s = "P" if sub_ok else f"F({sub.get('value','?')})"
        tag = "**YES**" if all_pass else "no"
        md += (f"| {r['variant']} | "
               f"{r['sharpe']:+.3f} | {r['turnover']:.3f} | "
                f"{r['fitness']:+.3f} | {r['checks_passed']}/{r['checks_total']} | "
                f"{c} | {s} | {sc.get('value','-')} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | - | - | no |  "
               f"{r.get('error','?')[:80]}\n")
    md += f"\n**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS): {len(survivors)}/{len(results)}**\n"
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
