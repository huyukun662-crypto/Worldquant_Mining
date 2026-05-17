"""Round 2 for user factor 3: structural changes since settings alone
cannot fix the fundamental TO > 1.0 problem on this signal.

Approaches tried in this round:
  A) Add news_pct gate (proven turnover killer)
  B) Add ts_decay_linear smoothing
  C) Fuse with IV+short proven backbone (like we did for F1/F2)
  D) Combine with insider sentiment
  E) Conditional gating on the signal's own extreme
"""

from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tune_user_factor_3 import (  # noqa: E402
    TrialResult, submit, fetch_self_corr, FIXED_SETTINGS, _load,
    VENDOR, REPO, log,
)


NEWS_GATE = ("gate = (ts_backfill(news_pct_90min, 5) < 1) * "
             "(ts_rank(abs(news_pct_30min), 60) > 0.80);")

# The base signal from the user (E4 was the best baseline):
BASE_SIGNAL = ("-group_neutralize("
               "ts_zscore(ts_delay(news_mins_20_chg, 1), 60), "
               "subindustry)")


CANDIDATES_3B: list[tuple[str, str, dict]] = [

    # === A. news_pct gate around the signal =========================
    ("3b_1_signal_news_gated",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signal, 5), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 4,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    # === B. heavy ts_decay (5d, 10d) ================================
    ("3b_2_decay10",
     f"signal = {BASE_SIGNAL};\n"
     "ts_decay_linear(signal, 10)",
     {"delay": 0, "universe": "TOP3000", "decay": 0,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    ("3b_3_decay20",
     f"signal = {BASE_SIGNAL};\n"
     "ts_decay_linear(signal, 20)",
     {"delay": 0, "universe": "TOP3000", "decay": 0,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    # === C. Fuse with IV+short proven backbone ======================
    # Take just the underlying news signal as additional cold input.
    # Note: convert the news-mins signal to delay-1 compatible.
    ("3b_4_fuse_iv_short",
     "n = ts_zscore(ts_delay(news_mins_20_chg, 1), 60);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness) - 0.3 * quantile(n);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"delay": 1, "universe": "TOP3000", "decay": 4,
      "truncation": 0.02, "neutralization": "SUBINDUSTRY", "pasteurization": "ON"}),

    # === D. Fuse with insider + IV ==================================
    ("3b_5_fuse_ins_iv",
     "n = ts_zscore(ts_delay(news_mins_20_chg, 1), 60);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.4 * quantile(ins) - 0.3 * quantile(n);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"delay": 1, "universe": "TOP3000", "decay": 4,
      "truncation": 0.02, "neutralization": "SUBINDUSTRY", "pasteurization": "ON"}),

    # === E. Self-gate on extreme signal =============================
    # Trade only when the news signal itself is extreme.
    ("3b_6_self_gate",
     f"signal = {BASE_SIGNAL};\n"
     "self_gate = ts_rank(abs(signal), 60) > 0.85;\n"
     "trade_when(self_gate, ts_decay_linear(signal, 10), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 4,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),

    # === F. news_pct gate at TOP500 with delay=0 (best from prior) ==
    ("3b_7_gate_top500",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signal, 5), -1)",
     {"delay": 0, "universe": "TOP500", "decay": 4,
      "truncation": 0.02, "neutralization": "SECTOR", "pasteurization": "ON"}),

    # === G. ts_decay_linear with explicit large window + gate =======
    ("3b_8_strong_smoothing",
     f"signal = {BASE_SIGNAL};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signal, 20), -1)",
     {"delay": 0, "universe": "TOP3000", "decay": 8,
      "truncation": 0.08, "neutralization": "INDUSTRY", "pasteurization": "ON"}),
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
    for i, (label, expr, settings) in enumerate(CANDIDATES_3B, 1):
        log.info(f"=== 3b [{i}/{len(CANDIDATES_3B)}] {label} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
        res = submit(cm.session, label, expr, settings)
        results.append(res)
        if not res.ok:
            log.warning(f"   FAILED: {res.error[:160]}")
        else:
            log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} chk={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        all_trials = prior + [asdict(r) for r in results]
        with open(out_path, "w") as f:
            json.dump(all_trials, f, indent=2)

    log.info("=== pass 2: self-correlation ===")
    for r in results:
        if not r.ok or not r.alpha_id: continue
        sc, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=90)
        r.self_corr = sc
        log.info(f"   {r.alpha_id} self_corr={sc} ({st})")
    with open(out_path, "w") as f:
        json.dump(prior + [asdict(r) for r in results], f, indent=2)

    # Report
    pass_bar = [r for r in results if r.ok and r.sharpe > 1.25
                 and r.turnover < 0.25 and r.fitness >= 1.0]
    print()
    print("=" * 130)
    print(f"### 3b: {len(pass_bar)} pass SH>1.25 + TO<0.25 + FIT>=1.0")
    print(f"{'#':<3}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7}  "
           f"{'label':<25} alpha_id")
    ok = sorted([r for r in results if r.ok], key=lambda r: r.sharpe, reverse=True)
    for j, r in enumerate(ok, 1):
        sc = f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        marker = "★" if (r in pass_bar) else " "
        print(f"{marker}{j:<2}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}"
               f"{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7}  "
               f"{r.expr_label:<25} {r.alpha_id}")
    print("=" * 130)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
