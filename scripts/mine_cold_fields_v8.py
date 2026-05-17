"""Round 9: exploit round-8 winners, try VECTOR analyst operators,
and explore more operator combinations.

Round-8 winners to extend:
  r9   quantile_iv_short   SH=2.030  -> apply quantile to other field combos
  r12  signed_power3_iv    SH=1.610  -> try other exponents / signals
  r5   signed_power2       SH=1.530  -> combine with quantile

Untouched operator families:
  vec_*  (vec_avg, vec_count, vec_max, vec_sum, vec_stddev)
         operate on VECTOR fields (analyst estimates: anl4_*)
  ts_decay_exponential  alternative to ts_decay_linear
  when_then / case      alternative conditional
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


CANDIDATES_V8: list[tuple[str, str, dict]] = [

    # ===== Apply quantile (round-8 winner) to OTHER field combos ======

    # Q1. quantile on insider+IV (was rank-sum in #4/#5 of old top 5)
    ("q1_quantile_insider_x_iv",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = quantile(iv) + quantile(ins);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # Q2. quantile on iv120 + short (extend the winner with iv120 tenor)
    ("q2_quantile_iv120_x_short",
     "iv = ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 1.0 * quantile(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # Q3. quantile on iv30 + short
    ("q3_quantile_iv30_x_short",
     "iv = ts_backfill(implied_volatility_call_30 - implied_volatility_put_30, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== signed_power variants =====================================

    # P1. signed_power(5) on IV alone (more extreme amplification than ^3)
    ("p1_signed_power5_iv",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(rank(iv) - 0.5, 5), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # P2. signed_power(3) on iv_x_short (combine winning ideas)
    ("p2_signed_power3_iv_x_short",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.75, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # P3. quantile + signed_power double transform
    ("p3_quantile_signed_power",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.75, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== VECTOR analyst operators (vec_*) ==========================

    # A1. vec_avg of EPS estimate mean (analyst expectations)
    ("a1_vec_avg_eps_mean",
     "eps_mean = vec_avg(anl4_basicconqf_mean);\n"
     "ts_decay_linear(-rank(ts_zscore(ts_backfill(eps_mean, 30), 60)), 10)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # A2. vec_avg dispersion - vec_avg mean (analyst disagreement vs level)
    ("a2_vec_dispersion_signal",
     "high = vec_avg(anl4_basicconqf_high);\n"
     "low = vec_avg(anl4_basicconqf_low);\n"
     "mean = vec_avg(anl4_basicconqf_mean);\n"
     "disp = ts_backfill((high - low) / (abs(mean) + 0.01), 30);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(-rank(disp), 10), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # A3. analyst number-of-estimates as conviction proxy
    ("a3_vec_count_estimates",
     "n = vec_avg(anl4_basicconqf_numest);\n"
     "ts_decay_linear(rank(ts_zscore(ts_backfill(n, 60), 120)), 10)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== Other operator families ===================================

    # X1. ts_decay_exponential instead of linear on iv_x_short
    ("x1_decay_exp",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_exponential(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # X2. IV-based gate instead of news gate (high abs(iv_skew) -> trade)
    ("x2_iv_gated",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness);\n"
     "iv_gate = ts_rank(abs(iv), 60) > 0.85;\n"
     "trade_when(iv_gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # X3. when_then alternative to trade_when (test if exists)
    ("x3_when_then",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30);\n"
     "ts_decay_linear(when_then(ins > 0, -quantile(iv), quantile(iv)), 5)",
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V8, 1):
        log.info(f"=== v8 [{i}/{len(CANDIDATES_V8)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..9): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable: {len(deliverable)}")
    v8_results = [asdict(r) for r in results]
    print()
    print("ROUND 9 (v8) RESULTS:")
    print(f"{'#':<4}{'family':<32}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v8_results if r.get('ok')],
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
