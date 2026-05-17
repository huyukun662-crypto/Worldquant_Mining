"""Round 3c: push 3b.1 from SH=1.16 to SH>1.25.

3b.1 (news_pct gate + ts_decay_linear) is the best so far:
  SH=1.16, TO=0.146, FIT=2.28, alpha=mLqm7dd2

Just 0.09 SH short.  This round tries 6 focused variations.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tune_user_factor_3 import (  # noqa: E402
    TrialResult, submit, fetch_self_corr, _load, VENDOR, REPO, log,
)


NEWS_GATE = ("gate = (ts_backfill(news_pct_90min, 5) < 1) * "
             "(ts_rank(abs(news_pct_30min), 60) > 0.80);")

BASE_SIGNAL = ("-group_neutralize("
               "ts_zscore(ts_delay(news_mins_20_chg, 1), 60), "
               "subindustry)")


CANDIDATES_3C: list[tuple[str, str, dict]] = [

    # === 1. 3b.1 + signed_power(., 3) amp ===========================
    ("3c_1_amp3",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(signal, 3), 5), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 4,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    # === 2. 3b.1 + signed_power(., 5) amp ===========================
    ("3c_2_amp5",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(signal, 5), 5), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 4,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    # === 3. 3b.1 + signed_power(rank-based) =========================
    # Re-rank, then signed_power for extreme amplification
    ("3c_3_amp_rank",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear("
       "signed_power(rank(signal) - 0.5, 3), 5), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 4,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    # === 4. 3b.1 + signed_power on amplified decay ===================
    ("3c_4_double_decay_amp",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, signed_power(ts_decay_linear(signal, 10), 3), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 4,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    # === 5. 3b.1 with truncation=0.02 (tighter) =====================
    ("3c_5_trunc02",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signal, 5), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 4,
      "truncation": 0.02, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    # === 6. 3b.1 SUBINDUSTRY neut + trunc=0.02 ======================
    ("3c_6_subindustry",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signal, 5), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 4,
      "truncation": 0.02, "neutralization": "SUBINDUSTRY", "pasteurization": "ON"}),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_USER_FACTOR_3_TUNE.json"
    prior = []
    if out_path.exists():
        old = json.load(open(out_path))
        prior = old if isinstance(old, list) else []
        log.info(f"loaded {len(prior)} prior trials")

    results: list[TrialResult] = []
    for i, (label, expr, settings) in enumerate(CANDIDATES_3C, 1):
        log.info(f"=== 3c [{i}/{len(CANDIDATES_3C)}] {label} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
        res = submit(cm.session, label, expr, settings)
        results.append(res)
        if not res.ok:
            log.warning(f"   FAILED: {res.error[:160]}")
        else:
            log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} chk={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        with open(out_path, "w") as f:
            json.dump(prior + [asdict(r) for r in results], f, indent=2)

    log.info("=== pass 2: self-correlation ===")
    for r in results:
        if not r.ok or not r.alpha_id: continue
        sc, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=90)
        r.self_corr = sc
        log.info(f"   {r.alpha_id} self_corr={sc} ({st})")
    with open(out_path, "w") as f:
        json.dump(prior + [asdict(r) for r in results], f, indent=2)

    pass_bar = [r for r in results if r.ok and r.sharpe > 1.25
                 and r.turnover < 0.25 and r.fitness >= 1.0]
    print()
    print("=" * 130)
    print(f"### 3c: {len(pass_bar)} pass SH>1.25 + TO<0.25 + FIT>=1.0")
    ok = sorted([r for r in results if r.ok], key=lambda r: r.sharpe, reverse=True)
    print(f"{'#':<3}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7}  {'label':<22} alpha_id")
    for j, r in enumerate(ok, 1):
        sc = f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        marker = "★" if (r in pass_bar) else " "
        print(f"{marker}{j:<2}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}"
               f"{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7}  "
               f"{r.expr_label:<22} {r.alpha_id}")
    print("=" * 130)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
