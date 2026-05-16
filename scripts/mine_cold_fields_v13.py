"""Round 14 (v13): CHANGE OF DIRECTION.

Prior rounds saturated:
  * IV skew (call - put)
  * mdl177_5shortsentimentfactor_lend_supply
  * news_pct gate
  * rank-sum / quantile-sum with signed_power amp

New directions in this round:
  A) Pure social media (snt_buzz_*, scl12_*) -- barely tested, no IV, no mdl177
  B) Pure insider + PCR + social combos
  C) Time-series momentum (ts_delta, ts_returns) on cold fields
  D) New mdl177 *families* (deepvaluefactor, pricemomentumfactor) --
     completely different math from 5shortsentimentfactor; conceptually
     orthogonal value/momentum signals.  If user wants ALL mdl177
     banned, the v13_8/9/10 candidates can be dropped.
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


CANDIDATES_V13: list[tuple[str, str, dict]] = [

    # === A. Pure social media (snt_*, scl12_*) =======================
    # 1. Pure social: scl12_sentiment + snt_value + snt_buzz_ret
    ("v13_1_pure_social",
     "sent = ts_backfill(scl12_sentiment_fast_d1, 10);\n"
     "val  = ts_backfill(snt_value_fast_d1, 10);\n"
     "ret  = ts_backfill(snt_buzz_ret_fast_d1, 10);\n"
     "score = quantile(sent) + 0.5 * quantile(val) + 0.3 * quantile(ret);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.4, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 2. Buzz spike with HV-calm gate (no news_pct, no mdl177, no IV)
    ("v13_2_social_hv_calm",
     "buzz = ts_backfill(snt_buzz_fast_d1, 10);\n"
     "ret  = ts_backfill(snt_buzz_ret_fast_d1, 10);\n"
     "hv = ts_backfill(historical_volatility_30, 5);\n"
     "vov = ts_std_dev(hv, 30);\n"
     "calm = ts_rank(vov, 60) < 0.30;\n"
     "score = quantile(buzz) + 0.5 * quantile(ret);\n"
     "trade_when(calm, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === B. Insider + PCR + social (no IV, no mdl177) ================
    # 3. Insider + PCR + social 3-way (truly diversified)
    ("v13_3_insider_pcr_social",
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "pc = ts_backfill(pcr_oi_30 - pcr_oi_180, 5);\n"
     "sent = ts_backfill(scl12_sentiment_fast_d1, 10);\n"
     "score = quantile(ins) - 0.5 * quantile(pc) + 0.3 * quantile(sent);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === C. Time-series MOMENTUM on cold fields ======================
    # 4. Insider sentiment momentum (5-day change in css)
    ("v13_4_insider_momentum",
     "ts_5  = ts_backfill(rp_css_insider, 5);\n"
     "ts_30 = ts_backfill(rp_css_insider, 30);\n"
     "mom = ts_5 - ts_30;\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(mom), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 5. PCR_OI momentum (change in option positioning)
    ("v13_5_pcr_momentum",
     "ts_5  = ts_backfill(pcr_oi_30, 5);\n"
     "ts_30 = ts_backfill(pcr_oi_30, 30);\n"
     "mom = ts_5 - ts_30;\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(-rank(mom), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === D. Cross-asset reversal: cold signal x sign(returns) =========
    # 6. IV skew conditioned by past return sign (regime-dependent)
    ("v13_6_iv_x_returns_sign",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "r_sign = sign(ts_mean(returns, 5));\n"
     "conditioned = iv * r_sign;\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(conditioned), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === E. mdl177 NEW families (NOT 5shortsentimentfactor) ==========
    # 7. mdl177_pricemomentumfactor_rsi26w as primary signal (momentum)
    ("v13_7_rsi26w_pure",
     "rsi = ts_backfill(mdl177_pricemomentumfactor_rsi26w, 30);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(quantile(-rsi) - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 8. Deep-value composite (book/price, EBITDA/P, FCF/P)
    ("v13_8_deepvalue_composite",
     "bp = ts_backfill(mdl177_2_deepvaluefactor_bp, 30);\n"
     "eb = ts_backfill(mdl177_2_deepvaluefactor_ebitdap, 30);\n"
     "fc = ts_backfill(mdl177_2_deepvaluefactor_fcfp, 30);\n"
     "score = quantile(bp) + quantile(eb) + quantile(fc);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score / 3 - 0.5, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 9. Value + IV stack (deep value + options)
    ("v13_9_value_iv_stack",
     "bp = ts_backfill(mdl177_2_deepvaluefactor_bp, 30);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.5 * quantile(bp);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 10. 5-year relative value stack
    ("v13_10_relvalue_5y",
     "bp = ts_backfill(mdl177_2_5yearrelativevaluefactor_rel5ybp, 30);\n"
     "eb = ts_backfill(mdl177_2_5yearrelativevaluefactor_rel5yebitdap, 30);\n"
     "fc = ts_backfill(mdl177_2_5yearrelativevaluefactor_rel5yfcfp, 30);\n"
     "score = quantile(bp) + quantile(eb) + quantile(fc);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score / 3 - 0.5, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V13, 1):
        log.info(f"=== v13 [{i}/{len(CANDIDATES_V13)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..14): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable: {len(deliverable)}")
    v13_results = [asdict(r) for r in results]
    print()
    print("ROUND 14 (v13) RESULTS  -- new direction (social/momentum/value):")
    print(f"{'#':<4}{'family':<32}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v13_results if r.get('ok')],
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
