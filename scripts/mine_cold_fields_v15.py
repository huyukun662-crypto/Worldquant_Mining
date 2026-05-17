"""Round 17 (v15): rescue the two user-supplied fundamental factors.

F1 and F2 standalone topped out at SH 0.92 and 1.07 in the
setting-only tune.  This round combines them with our proven
winning template (trade_when news_gate + signed_power amp +
IV-skew backbone) and a few standalone improvements.

User factors:
  F1 raw signal:
    f1 = (40 - ts_arg_max(
            ts_delay(fn_comp_non_opt_nonvested_number_a, 1), 40)) / 40
       (time-since-peak of non-vested comp count; small = recent peak)
  F2 raw signal:
    f2 = group_rank(ts_delay(fnd2_a_dfdtxava, 1), subindustry)
       (industry-relative deferred tax asset signal)
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (  # noqa: E402
    CandidateResult, submit, fetch_self_corr, FIXED_SETTINGS, _load,
    VENDOR, REPO, log,
)


NEWS_GATE = ("gate = (ts_backfill(news_pct_90min, 5) < 1) * "
             "(ts_rank(abs(news_pct_30min), 60) > 0.80);")

F1_RAW = ("(40 - ts_arg_max("
          "ts_delay(fn_comp_non_opt_nonvested_number_a, 1), 40)) / 40")
F2_RAW = ("group_rank(ts_delay(fnd2_a_dfdtxava, 1), subindustry)")


CANDIDATES_V15: list[tuple[str, str, dict]] = [

    # === 1. F1 + IV stack + news_gate + signed_power ================
    ("v15_1_F1_x_iv",
     f"f1 = {F1_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.5 * quantile(f1);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 2. F2 + IV stack ===========================================
    ("v15_2_F2_x_iv",
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.5 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 3. F1 + IV + short 3-way ===================================
    ("v15_3_F1_iv_short",
     f"f1 = {F1_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness) + 0.3 * quantile(f1);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 4. F2 + IV + short 3-way ===================================
    ("v15_4_F2_iv_short",
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness) + 0.3 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 5. F1 + F2 + IV (pure fundamentals + IV stack) =============
    ("v15_5_F1_F2_iv",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.3 * quantile(f1) + 0.3 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 6. F1 + insider stack ======================================
    ("v15_6_F1_insider_iv",
     f"f1 = {F1_RAW};\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.3 * quantile(ins) + 0.3 * quantile(f1);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 7. F1 with longer arg_max window (60-day vs 40-day) ========
    ("v15_7_F1_long_window",
     "f1_long = (60 - ts_arg_max("
       "ts_delay(fn_comp_non_opt_nonvested_number_a, 1), 60)) / 60;\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.5 * quantile(f1_long);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 8. F2 with ts_delta (change in deferred tax asset) =========
    ("v15_8_F2_delta",
     "f2_delta = ts_delta(ts_delay(fnd2_a_dfdtxava, 1), 30);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.5 * quantile(f2_delta);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 9. F1 + F2 + IV + GARP (4-way ultra-stack) =================
    ("v15_9_F1_F2_iv_garp",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.3*quantile(g) + 0.2*quantile(f1) + 0.2*quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 10. F2 with signed_power amp only (no IV) ==================
    ("v15_10_F2_signed_power_only",
     f"f2 = {F2_RAW};\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(f2 - 0.5, 3), 5), -1)",
     {"decay": 8, "truncation": 0.10, "neutralization": "INDUSTRY"}),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_COLD_FACTORS.json"
    prior = []
    if out_path.exists():
        old = json.load(open(out_path))
        prior = old.get("all_trials") or (old if isinstance(old, list) else [])
        log.info(f"loaded {len(prior)} prior trials")

    results: list[CandidateResult] = []
    for i, (family, expr, settings) in enumerate(CANDIDATES_V15, 1):
        log.info(f"=== v15 [{i}/{len(CANDIDATES_V15)}] family={family} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
        res = submit(cm.session, family, expr, settings)
        results.append(res)
        if not res.ok:
            log.warning(f"   FAILED: {res.error[:160]}")
        else:
            log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        all_trials = prior + [asdict(r) for r in results]
        with open(out_path, "w") as f:
            json.dump({"all_trials": all_trials}, f, indent=2)

    log.info("=== pass 2: self-correlation ===")
    for r in results:
        if not r.ok or not r.alpha_id: continue
        sc, top, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=90)
        r.self_corr = sc
        if top:
            r.self_corr_peer = top.get("id")
            r.self_corr_peer_sharpe = top.get("sharpe")
        sc_s = f"{sc:.3f}" if sc is not None else "?"
        peer = f"{top['id']}@SH{top['sharpe']}" if top else "(none)"
        log.info(f"   {r.alpha_id} self_corr={sc_s} ({st}) peer={peer}")

    def sc_pass(r):
        if r.get("self_corr") is None: return False
        if abs(r["self_corr"]) < 0.70: return True
        peer_sh = r.get("self_corr_peer_sharpe")
        return (isinstance(peer_sh, (int, float))
                and r["sharpe"] >= 1.10 * peer_sh)

    all_trials = prior + [asdict(r) for r in results]
    deliverable = [r for r in all_trials
                    if r.get("ok") and r["sharpe"] > 1.25
                    and r["turnover"] < 0.25 and sc_pass(r)]
    deliverable.sort(key=lambda r: r["sharpe"], reverse=True)

    print()
    print("=" * 130)
    print(f"All trials OK (rounds 1..17): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable: {len(deliverable)}")
    v15_results = [asdict(r) for r in results]
    print()
    print("ROUND 17 (v15) RESULTS  -- F1/F2 fusion attempts:")
    print(f"{'#':<4}{'family':<32}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v15_results if r.get('ok')],
                                   key=lambda x: x['sharpe'], reverse=True), 1):
        deliv = (r.get("ok") and r["sharpe"] > 1.25 and r["turnover"] < 0.25
                  and sc_pass(r))
        marker = "★" if deliv else " "
        sc = f"{r['self_corr']:+.3f}" if r.get("self_corr") is not None else "  -  "
        print(f"{marker}{i:<3}{r['family']:<32}{r['sharpe']:7.3f}{r['turnover']:7.3f}"
               f"{r['fitness']:7.3f} {r['checks_passed']:>2}/{r['checks_total']:<2}"
               f"{sc:>7} {r['alpha_id']:<10}")
    failures = [asdict(r) for r in results if not r.ok]
    if failures:
        print()
        print("FAILED:")
        for r in failures:
            print(f"   {r['family']:<32}  {r['error'][:120]}")
    print("=" * 130)

    with open(out_path, "w") as f:
        json.dump({"all_trials": all_trials}, f, indent=2)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
