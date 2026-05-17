"""Round 8: act on round-7 leads + try more new operator families.

Round-7 leads:
  G7 ivrp_residual    SH=-0.73  ->  flip sign + try simpler IVRP
  G1 group_rank_ins   SH=+0.82  ->  add the proven news_gate wrapper
  G6 iv_smile_curv    SH=-0.39  ->  flip + simpler variant

Untried operator families:
  signed_power(x, p)     non-linear amplification of extremes
  bucket(x, range)        discretize continuous -> bucketed levels
  densify(x, n_buckets)   alternative discretization
  pasteurize_low_high()   clip distribution tails
  when_then / case        alternative conditional
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


CANDIDATES_V7: list[tuple[str, str, dict]] = [

    # ====== Recovery: round-7 leads with sign-flip or proven gate =====
    # R1. ivrp_residual sign-flipped: high IVRP -> short -> negate -> long
    ("r1_ivrp_residual_flipped",
     "iv = ts_backfill(implied_volatility_call_60, 5);\n"
     "hv = ts_backfill(historical_volatility_60, 5);\n"
     "resid = ts_regression(iv, hv, 120);\n"
     "ts_decay_linear(rank(resid), 10)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # R2. group_rank insider + news_gate (G1 had FIT=1.46 but no gate)
    ("r2_group_rank_insider_gated",
     "raw = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(group_rank(raw, sector), 10), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "NONE"}),

    # R3. Simpler IVRP = IV - HV directly (no regression), news-gated
    ("r3_ivrp_simple_gated",
     "iv = ts_backfill(implied_volatility_call_60, 5);\n"
     "hv = ts_backfill(historical_volatility_60, 5);\n"
     "ivrp = iv - hv;\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(-rank(ivrp), 10), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # R4. group_rank insider by industry (G1 used sector)
    ("r4_group_rank_insider_industry",
     "raw = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "ts_decay_linear(group_rank(raw, industry), 10)",
     {"decay": 6, "truncation": 0.02, "neutralization": "NONE"}),

    # ====== New operators: signed_power amplifies extremes ============
    # R5. iv_x_short winner with signed_power(2) amplifying the rank.
    ("r5_signed_power_iv_x_short",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 2), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ====== bucket() discretization ===================================
    # R6. iv_x_short winner with bucket(score, 0.1) -> 10 levels.
    ("r6_bucket_iv_x_short",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(bucket(score, range=\"0,1,0.1\"), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ====== densify() bucketization ==================================
    # R7. densify on insider rank.
    ("r7_densify_insider",
     "raw = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "ts_decay_linear(densify(rank(raw)), 10)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ====== pasteurize on distribution tails ==========================
    # R8. Apply pasteurize to clamp IV+short score's distribution.
    ("r8_pasteurize_iv_short",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(pasteurize(score), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ====== ts_quantile / quantile transforms =========================
    # R9. quantile of iv_x_short score (alternative to rank).
    ("r9_quantile_iv_short",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ====== Combine winner structure with sign-flipped curvature =====
    # R10. Use IV smile curvature (G6) sign-flipped + news_gate.
    ("r10_smile_curvature_flipped",
     "callc = ts_backfill(implied_volatility_call_30 + implied_volatility_call_120 "
     "- 2 * implied_volatility_call_60, 5);\n"
     "putc  = ts_backfill(implied_volatility_put_30 + implied_volatility_put_120 "
     "- 2 * implied_volatility_put_60, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(callc + putc), 10), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ====== IVRP across multiple tenors ===============================
    # R11. Average IVRP across short and medium tenors.
    ("r11_ivrp_multi_tenor",
     "iv30 = ts_backfill(implied_volatility_call_30, 5);\n"
     "iv90 = ts_backfill(implied_volatility_call_90, 5);\n"
     "hv30 = ts_backfill(historical_volatility_30, 5);\n"
     "hv90 = ts_backfill(historical_volatility_90, 5);\n"
     "ivrp = (iv30 - hv30 + iv90 - hv90) / 2;\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(-rank(ivrp), 10), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ====== power-3 amplification of IV alone =========================
    # R12. signed_power(3) on iv60 skew (cube amplification) + gate.
    ("r12_signed_power3_iv",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(rank(iv) - 0.5, 3), 5), -1)",
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V7, 1):
        log.info(f"=== v7 [{i}/{len(CANDIDATES_V7)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..8): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable (SH>1.25 AND TO<0.25 AND sc OK): {len(deliverable)}")
    v7_results = [asdict(r) for r in results]
    print()
    print("ROUND 8 (v7) RESULTS:")
    print(f"{'#':<4}{'family':<32}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v7_results if r.get('ok')],
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
