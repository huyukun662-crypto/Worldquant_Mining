"""Round 72: GTJA191 batch 2 -- 8 different skeletons.

R70 batch 1 results: GTJA002 was the only one strong (SH +1.74) but
TO 0.70. R71 confirmed GTJA002's Pareto frontier can't break SH 1.5
^ TO 0.20 simultaneously (best: SH 1.83 / TO 0.29 or SH 0.89 / TO 0.21).

This round samples 8 different GTJA191 skeletons, all structurally
distinct from BB range-vol (already covered) and price-position
(GTJA002 family). Pre-filter: only ops known to be available on this
account tier; no ts_max, ts_skewness, ts_moment, REGBETA, BANCHMARKINDEX.

  GTJA046  multi-MA convergence (3/6/12/24)            reversed
  GTJA063  RSI 6d (Wilder)                             reversed
  GTJA106  raw 20d momentum                            reversed
  GTJA133  arg_max(H,20) - arg_min(L,20)               natural
  GTJA134  12d return x volume                         natural
  GTJA148  open-vs-volume-corr vs open-from-low        reversed
  GTJA158  (H-MA15) - (L-MA15) / C                     reversed
  GTJA178  1d return x volume                          reversed

All wrapped: zscore(ts_decay_linear(<core>, 8)).
Settings: TOP3000, delay=1, decay=8, trunc=0.08, SUBINDUSTRY, pasteur ON.
Gate: SH >= 1.5 ^ TO < 0.20 ^ ALL 8 WQ checks PASS ^ self_corr < 0.7 vs A1nnxAdw.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r72")
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


def W(core: str, decay: int = 8) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


DC = "subtract(close, ts_delay(close, 1))"   # delta close 1d

# 046 multi-MA convergence ratio; high ratio = overheated => reverse
GTJA046 = W(
    f"reverse(divide(add(add(ts_mean(close,3), ts_mean(close,6)), "
    f"add(ts_mean(close,12), ts_mean(close,24))), multiply(4, close)))"
)
# 063 RSI 6d. max(x,0) emulated via multiply(greater(x,0), x)
UP = f"multiply(greater({DC}, 0), {DC})"
GTJA063 = W(
    f"reverse(divide(ts_decay_linear({UP}, 6), ts_decay_linear(abs({DC}), 6)))"
)
# 106 raw 20d momentum reversed
GTJA106 = W(f"reverse(subtract(close, ts_delay(close, 20)))")
# 133 days-since-high minus days-since-low
GTJA133 = W(f"subtract(ts_arg_max(high, 20), ts_arg_min(low, 20))")
# 134 12d return x volume
RET12 = "divide(subtract(close, ts_delay(close, 12)), ts_delay(close, 12))"
GTJA134 = W(f"multiply({RET12}, volume)")
# 148 (RANK(CORR(OPEN, SUM(MEAN(VOL,60),9), 6)) < RANK(OPEN - TSMIN(OPEN,14))) * -1
GTJA148 = W(
    f"multiply(-1, less("
    f"rank(ts_corr(open, ts_sum(ts_mean(volume, 60), 9), 6)),"
    f"rank(subtract(open, ts_min(open, 14)))))"
)
# 158 (H - SMA(C,15)) - (L - SMA(C,15)) / C  reversed
MA15 = "ts_decay_linear(close, 15)"
GTJA158 = W(
    f"reverse(divide(subtract(subtract(high, {MA15}), subtract(low, {MA15})), close))"
)
# 178 1d return x volume reversed
RET1 = f"divide({DC}, ts_delay(close, 1))"
GTJA178 = W(f"reverse(multiply({RET1}, volume))")


VARIANTS = [
    {"label": "GTJA046_meanconv_rev",      "expression": GTJA046},
    {"label": "GTJA063_rsi6_rev",          "expression": GTJA063},
    {"label": "GTJA106_mom20_rev",         "expression": GTJA106},
    {"label": "GTJA133_hl_day_balance",    "expression": GTJA133},
    {"label": "GTJA134_volwt_mom12",       "expression": GTJA134},
    {"label": "GTJA148_open_vol_corr",     "expression": GTJA148},
    {"label": "GTJA158_hl_to_ma_rev",      "expression": GTJA158},
    {"label": "GTJA178_volwt_mom1_rev",    "expression": GTJA178},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r72_gtja191_batch2_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R72: GTJA191 batch 2 -- 8 diverse skeletons (MA conv, RSI, raw mom, "
        "H/L day balance, vol-wt mom, open-vol corr, H-L to MA). Gate: "
        "SH>=1.5 ^ TO<0.20 ^ all 8 checks PASS ^ self_corr<0.7 vs A1nnxAdw.\n"
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
    md = "# R72 GTJA191 batch 2\n\n"
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
