"""Round 66: BB Garman-Klass with acceleration / cross-time / multiplicative
amplification.

Story so far:
  R63 BB GK range vol      SH +1.31  TO 0.053  FIT +2.38   (sharp plateau)
  R64 BB-amplification     SH ~1.32 ceiling, combos destroy
  R65 8 new skeletons      SH ceiling ~1.24 (QQ); rest weak

The R45-R47 SH 2.2-2.3 winners (TT3 ZY_SUBIN, VV4 rv20-acc2-D25, UU4
realized-retvol) all used acceleration structures on ts_std_dev. BB
hasn't been tried with that envelope. This round mirrors the rv-acc
winning recipe onto BB:

  YY  BB acceleration     reverse(ts_delta(ts_mean(range_sq,5), 20))
  ZZ  BB cross-time z     reverse(ts_zscore(ts_mean(range_sq,5), 60))
  AAA BB second-order acc reverse(ts_delta(ts_delta(rs_mean5, 10), 20))
  BBB BB x rv (both rev)  reverse(BB) x reverse(ts_std_dev(returns,20))
  CCC BB signed_power 2   amplify tails
  DDD BB rank-wrap        rank instead of zscore at output
  EEE Overnight gap accel reverse(ts_zscore(ts_mean(opc_sq,5), 60))
  FFF Full GK accel       reverse(ts_delta(ts_mean(rs_sq-co_sq, 5), 20))

Same gate: SH >= 1.5 ^ TO < 0.20 ^ conc+sub PASS.
"""
from __future__ import annotations
import datetime as dt, importlib.util, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r66")
REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def base_settings() -> dict:
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 8, "truncation": 0.08,
        "neutralization": "SUBINDUSTRY", "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR",
        "visualization": False, "maxTrade": "OFF", "testPeriod": "P0Y0M",
    }


def W(core: str, decay: int = 30) -> str:
    return f"zscore(ts_decay_linear({core}, {decay}))"


RS = "signed_power(log(divide(high, low)), 2)"
CO = "signed_power(log(divide(close, open)), 2)"
OPC = "signed_power(log(divide(open, ts_delay(close, 1))), 2)"
BB20 = f"ts_mean({RS}, 20)"
BB5 = f"ts_mean({RS}, 5)"

# YY  BB first-order acceleration (range-vol expansion velocity, reversed)
YY = W(f"reverse(ts_delta({BB5}, 20))", decay=30)
# ZZ  BB cross-time z-score (recent range vs 60d distribution)
ZZ = W(f"reverse(ts_zscore({BB5}, 60))", decay=30)
# AAA BB second-order acceleration (mirror VV4 rv20-acc2 structure)
AAA = W(f"reverse(ts_delta(ts_delta({BB5}, 10), 20))", decay=25)
# BBB BB x reverse(ts_std_dev): combine the two reversed vol proxies
BBB = W(
    f"multiply(reverse({BB20}), reverse(ts_std_dev(returns, 20)))",
    decay=30,
)
# CCC BB signed_power 2 (amplify tails)
CCC = W(f"signed_power(reverse({BB20}), 2)", decay=30)
# DDD BB rank-wrap (rank as outer, not zscore)
DDD = f"rank(ts_decay_linear(reverse({BB20}), 30))"
# EEE Overnight gap cross-time z-score
EEE = W(f"reverse(ts_zscore(ts_mean({OPC}, 5), 60))", decay=30)
# FFF Full GK acceleration (R65 QQ + ts_delta)
FFF = W(
    f"reverse(ts_delta(ts_mean(subtract({RS}, {CO}), 5), 20))",
    decay=30,
)

VARIANTS = [
    {"label": "YY_BB_accel1", "expression": YY},
    {"label": "ZZ_BB_zscore60", "expression": ZZ},
    {"label": "AAA_BB_acc2_D25", "expression": AAA},
    {"label": "BBB_BB_x_rv20", "expression": BBB},
    {"label": "CCC_BB_signedpow2", "expression": CCC},
    {"label": "DDD_BB_rank_wrap", "expression": DDD},
    {"label": "EEE_overnight_zscore", "expression": EEE},
    {"label": "FFF_fullGK_accel", "expression": FFF},
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
    session_id = f"{dt.datetime.now():%Y%m%d}_us_equity_r66_bb_acceleration_wq"
    session_dir = REPO / "logs" / session_id
    for sub in ("inputs", "working", "outputs"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    (session_dir / "inputs" / "objective.md").write_text(
        "R66: mirror R45-R47 rv-acceleration winners onto BB Garman-Klass "
        "range vol (BB capped at SH ~1.32 single-source). Try ts_delta, "
        "ts_zscore, BB x rv combo, signed_power amp, rank-wrap.\n"
    )
    log.info(f"Session: {session_dir}")
    results = []
    for i, v in enumerate(VARIANTS, 1):
        log.info(f"  [{i}/{len(VARIANTS)}] {v['label']}")
        log.info(f"      expr: {v['expression']}")
        settings = base_settings()
        try:
            res = r5.submit(cm.session, v["expression"], settings)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        entry = {"variant": v["label"], "expression": v["expression"], **res}
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
    md = "# R66 BB acceleration / cross-time / combos\n\n"
    md += ("| variant | SH | TO | FIT | conc | sub | passes? |\n"
           "|---|---:|---:|---:|---|---|---|\n")
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
                f"{r['fitness']:+.3f} | {c} | {s} | {tag} |\n")
    for r in [r for r in results if not r.get('ok')]:
        md += (f"| {r['variant']} | FAIL | - | - | - | - | no |  "
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
