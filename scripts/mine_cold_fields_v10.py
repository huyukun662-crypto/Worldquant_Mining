"""Round 11 (v10): 10 candidates deliberately AVOIDING the
implied_volatility_call/put_* x mdl177_5shortsentimentfactor_lend_supply
template that 21/23 deliverables share.

NEW field families (untouched in prior rounds):
  pcr_oi_*                                        option positioning ratio
  mdl177_5shortsentimentfactor_act_util/fee/...   other short-borrow signals
  historical_volatility_30/60/120                 realized vol only (no IV)
  news_atr_ratio standalone                       news-attention regime
  snt_buzz_ret_fast_d1, scl12_sentiment_fast_d1   social media
  rp_nip_insider                                  RavenPack news-influence
  news_main_vwap / news_eod_vwap                  intraday news pricing
  earnings_shortfall_metric                       fundamentals event

NEW operator usage:
  ts_skewness  distribution-shape over a window (untouched as primary)
  divide()     explicit unit-safe division (replaces "/ x" arithmetic)
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


CANDIDATES_V10: list[tuple[str, str, dict]] = [

    # === 1. PCR_OI term structure (NEW field family) ====================
    # Short-term P/C OI vs long-term. Contrarian: rising short-term puts
    # vs baseline -> bullish reversion.
    ("v10_1_pcr_termstructure_quantile",
     "pc = ts_backfill(pcr_oi_30 - pcr_oi_180, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_act_util, 30);\n"
     "stress = -ts_zscore(supply, 120);\n"
     "score = -quantile(pc) + 0.5 * quantile(stress);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 2. PCR_OI multi-tenor curvature (3-tenor combo) =================
    ("v10_2_pcr_curvature",
     "curv = ts_backfill(pcr_oi_30 + pcr_oi_180 - 2 * pcr_oi_90, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(-rank(curv), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 3. Short utilization (NOT lend_supply) =========================
    # Higher utilization -> crowded short -> contrarian long
    ("v10_3_short_util_signed_power",
     "u = ts_backfill(mdl177_5shortsentimentfactor_act_util, 30);\n"
     "z = ts_zscore(u, 120);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(quantile(-z) - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 4. HV regime ratio (NO IV AT ALL) ===============================
    # Short-term realized vol vs long-term, contrarian
    ("v10_4_hv_regime_ratio",
     "hv30 = ts_backfill(historical_volatility_30, 5);\n"
     "hv120 = ts_backfill(historical_volatility_120, 5);\n"
     "ratio = divide(hv30, hv120);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(-quantile(ratio), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 5. News-ATR-ratio standalone (cold news only, no IV) ============
    # Episodic news-attention spike, contrarian
    ("v10_5_news_atr_episodic",
     "atr = ts_backfill(news_atr_ratio, 10);\n"
     "z = ts_zscore(atr, 60);\n"
     "spike_gate = ts_rank(abs(z), 60) > 0.90;\n"
     "trade_when(spike_gate, ts_decay_linear(signed_power(quantile(-z) - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 6. rp_nip_insider standalone (untouched insider variant) ========
    # News-influence-percentile of insider events -- different from css/ess
    ("v10_6_rp_nip_insider",
     "nip = ts_backfill(rp_nip_insider, 30);\n"
     "z = ts_zscore(nip, 120);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(quantile(z) - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 7. News VWAP intraday divergence (unit-safe divide) =============
    ("v10_7_news_vwap_divergence",
     "ratio = divide(ts_backfill(news_main_vwap, 5), ts_backfill(news_eod_vwap, 5));\n"
     "z = ts_zscore(ratio, 60);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(z), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 8. ts_skewness of historical_volatility (NEW operator) ==========
    # Vol distribution skewness -- captures regime asymmetry
    ("v10_8_ts_skewness_hv",
     "hv = ts_backfill(historical_volatility_60, 5);\n"
     "skw = ts_skewness(hv, 60);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(-rank(skw), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 9. Earnings shortfall x dispersion (untouched combo) ============
    # Recent earnings disappointment combined with high analyst uncertainty
    ("v10_9_shortfall_x_dispersion",
     "sf = ts_backfill(earnings_shortfall_metric, 30);\n"
     "ed = ts_backfill(fy1_eps_estimate_dispersion_2, 30);\n"
     "score = -quantile(sf) - 0.5 * quantile(ed);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.0, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 10. Borrow fee spike + utilization stack ========================
    # Multi-signal short-borrow stress (NOT lend_supply)
    ("v10_10_borrow_fee_stack",
     "fee = ts_backfill(mdl177_5shortsentimentfactor_benchmark_fee, 30);\n"
     "util = ts_backfill(mdl177_5shortsentimentfactor_act_util, 30);\n"
     "dtc = ts_backfill(mdl177_5shortsentimentfactor_days_to_cover, 30);\n"
     "score = quantile(-fee) + 0.5 * quantile(-util) + 0.3 * quantile(-dtc);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V10, 1):
        log.info(f"=== v10 [{i}/{len(CANDIDATES_V10)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..11): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable: {len(deliverable)}")
    v10_results = [asdict(r) for r in results]
    print()
    print("ROUND 11 (v10) RESULTS:")
    print(f"{'#':<4}{'family':<36}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v10_results if r.get('ok')],
                                   key=lambda x: x['sharpe'], reverse=True), 1):
        deliv = (r.get("ok") and r["sharpe"] > 1.25 and r["turnover"] < 0.25
                  and sc_pass(r))
        marker = "★" if deliv else " "
        sc = f"{r['self_corr']:+.3f}" if r.get("self_corr") is not None else "  -  "
        print(f"{marker}{i:<3}{r['family']:<36}{r['sharpe']:7.3f}{r['turnover']:7.3f}"
               f"{r['fitness']:7.3f} {r['checks_passed']:>2}/{r['checks_total']:<2}"
               f"{sc:>7} {r['alpha_id']:<10}")
    failures = [asdict(r) for r in results if not r.ok]
    if failures:
        print()
        print("FAILED:")
        for r in failures:
            print(f"   {r['family']:<36}  {r['error'][:120]}")
    print("=" * 130)

    with open(out_path, "w") as f:
        json.dump({"all_trials": all_trials}, f, indent=2)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
