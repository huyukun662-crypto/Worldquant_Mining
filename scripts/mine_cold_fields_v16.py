"""Tune v15.9 (4-way F1+F2+IV+GARP) to push FIT >= 1.0.

User reported alpha 1YoXY666 fails LOW_FITNESS check (FIT=0.95
< 1.0 cutoff).  Base expression has SH=1.28, FIT=0.95, TO=0.051.

To raise FIT we need to raise SH (FIT ~= SH * margin_proxy).
The current weighting (IV=1.0, GARP=0.3, F1=0.2, F2=0.2) may
dilute the strong IV+GARP signal which alone gave SH=2.38, FIT=2.45.

10 candidates to try:
  1   drop F1 (weakest): IV + GARP + F2 only
  2   drop F2:           IV + GARP + F1 only
  3   drop F1 + F2:      IV + GARP only (known SH=2.38)
  4   higher weights on IV + GARP, smaller F1+F2 weights
  5   signed_power exponent 5 (more amp)
  6   different score offset 0.4
  7   IV tenor 90 instead of 60
  8   IV tenor 120
  9   add lend_supply tightness as 5th signal
  10  different decay 8 + INDUSTRY neut
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

F1_RAW = "(40 - ts_arg_max(ts_delay(fn_comp_non_opt_nonvested_number_a, 1), 40)) / 40"
F2_RAW = "group_rank(ts_delay(fnd2_a_dfdtxava, 1), subindustry)"


CANDIDATES_V16: list[tuple[str, str, dict]] = [

    # === 1. drop F1 (weakest): IV + GARP + F2 ======================
    ("v16_1_iv_garp_F2",
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.4 * quantile(g) + 0.3 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 2. drop F2: IV + GARP + F1 ================================
    ("v16_2_iv_garp_F1",
     f"f1 = {F1_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.4 * quantile(g) + 0.3 * quantile(f1);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 3. Boost IV+GARP weights, smaller F1/F2 ===================
    ("v16_3_iv_heavy_garp",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.5 * quantile(g) + 0.1 * quantile(f1) + 0.1 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 4. signed_power exponent 5 (more amp) ======================
    ("v16_4_signed_power_5",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.3 * quantile(g) + 0.2 * quantile(f1) + 0.2 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 5), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 5. score offset 0.4 (more left-tail concentration) ========
    ("v16_5_offset_04",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.3 * quantile(g) + 0.2 * quantile(f1) + 0.2 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.4, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 6. IV tenor 90 ============================================
    ("v16_6_iv90",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.3 * quantile(g) + 0.2 * quantile(f1) + 0.2 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 7. IV tenor 120 ===========================================
    ("v16_7_iv120",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.3 * quantile(g) + 0.2 * quantile(f1) + 0.2 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 8. Add short-borrow tightness as 5th signal ==============
    ("v16_8_5way_with_short",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.3*quantile(tightness) + 0.3*quantile(g) "
            "+ 0.15*quantile(f1) + 0.15*quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 9. decay=8 + INDUSTRY neut (smoother + different bucket) ==
    ("v16_9_decay8_industry",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = quantile(iv) + 0.3 * quantile(g) + 0.2 * quantile(f1) + 0.2 * quantile(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "INDUSTRY"}),

    # === 10. Use rank instead of quantile (different normalization) =
    ("v16_10_rank_not_quantile",
     f"f1 = {F1_RAW};\n"
     f"f2 = {F2_RAW};\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "g  = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "score = rank(iv) + 0.3 * rank(g) + 0.2 * rank(f1) + 0.2 * rank(f2);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.85, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V16, 1):
        log.info(f"=== v16 [{i}/{len(CANDIDATES_V16)}] family={family} ===")
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
    # Pass requires SH > 1.25 + TO < 0.25 + FIT >= 1.0 (LOW_FITNESS check)
    deliverable = [r for r in all_trials
                    if r.get("ok") and r["sharpe"] > 1.25
                    and r["turnover"] < 0.25
                    and r["fitness"] >= 1.0
                    and sc_pass(r)]
    deliverable.sort(key=lambda r: r["sharpe"], reverse=True)

    print()
    print("=" * 130)
    print(f"All trials OK (rounds 1..18): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable (SH>1.25 AND TO<0.25 AND FIT>=1.0 AND sc OK): {len(deliverable)}")
    v16_results = [asdict(r) for r in results]
    print()
    print("ROUND 18 (v16) RESULTS  -- fix v15.9 LOW_FITNESS:")
    print(f"{'#':<4}{'family':<32}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v16_results if r.get('ok')],
                                   key=lambda x: x['sharpe'], reverse=True), 1):
        deliv = (r.get("ok") and r["sharpe"] > 1.25 and r["turnover"] < 0.25
                  and r["fitness"] >= 1.0 and sc_pass(r))
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
