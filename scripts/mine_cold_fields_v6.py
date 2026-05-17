"""Round 7 (script suffix _v6 for cohesion with prior scripts):
deliberately move OFF the dominant template
    trade_when(news_gate, ts_decay_linear(rank(A)+w*rank(B), 5), -1)

Each candidate uses a structurally different idea or operator family:

  G1  group_rank(signal, sector/industry)            sector-relative ranking
  G2  group_neutralize(signal, group)                explicit bucketing
  G3  ts_corr(A, B, window)                          regime / co-movement
  G4  ts_co_kurtosis(A, B, window)                   higher co-moments
  G5  ts_arg_max(field, window)                      temporal location
  G6  IV smile curvature  C30 + C120 - 2*C60         3-tenor combination
  G7  ts_regression(IV, HV, ...).residual            regression-residual
  G8  if_else(cond, expr_pos, expr_neg)              conditional (no trade_when)
  G9  scale(winsorize(zscore(...), 3))               scale+winsorize normalize
  G10 ts_returns(historical_volatility_60, 5)        momentum on a cold field
  G11 ts_zscore(rank_change, window)                 rank-momentum
  G12 max(A, B) / min(A, B)                          envelope (not rank-sum)
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


CANDIDATES_V6: list[tuple[str, str, dict]] = [

    # G1 -- group_rank: sector-relative insider sentiment, then time-decay
    ("g1_group_rank_insider",
     "raw = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "ts_decay_linear(group_rank(raw, sector), 10)",
     {"decay": 6, "truncation": 0.02, "neutralization": "NONE"}),

    # G2 -- group_neutralize: IV skew, with industry mean removed within bucket
    ("g2_group_neutral_iv",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ts_decay_linear(group_neutralize(iv, industry), 5)",
     {"decay": 4, "truncation": 0.02, "neutralization": "NONE"}),

    # G3 -- ts_corr: news-price decoupling regime
    # When news attention is high but uncorrelated with returns -> regime
    # change. Negate so positive => buy.
    ("g3_news_price_decoupling",
     "ts_decay_linear(-ts_corr(news_atr_ratio, returns, 60), 10)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G4 -- ts_co_kurtosis: tail co-movement between IV skew and short borrow
    ("g4_co_kurtosis",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "ts_decay_linear(-ts_co_kurtosis(iv, supply, 120), 10)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G5 -- ts_arg_max: recency of historical volatility peak.
    # Recent peak (small arg_max value) -> recent vol shock -> revert.
    ("g5_arg_max_hv",
     "loc = ts_arg_max(historical_volatility_30, 60);\n"
     "ts_decay_linear(-rank(loc), 10)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G6 -- IV smile curvature: 3-tenor combination (not a pair difference).
    # C30 + C120 - 2 * C60  -- positive curvature means tails priced higher.
    # Combine with put-side for symmetric curvature.
    ("g6_iv_smile_curvature",
     "callc = ts_backfill(implied_volatility_call_30 + implied_volatility_call_120 "
     "- 2 * implied_volatility_call_60, 5);\n"
     "putc  = ts_backfill(implied_volatility_put_30 + implied_volatility_put_120 "
     "- 2 * implied_volatility_put_60, 5);\n"
     "ts_decay_linear(-rank(callc + putc), 10)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G7 -- ts_regression residual: IV minus its HV-explained component
    # (vol risk premium proxy).  Negate so high IVRP -> short.
    ("g7_ivrp_residual",
     "iv = ts_backfill(implied_volatility_call_60, 5);\n"
     "hv = ts_backfill(historical_volatility_60, 5);\n"
     "resid = ts_regression(iv, hv, 120);\n"
     "ts_decay_linear(-rank(resid), 10)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G8 -- if_else: directional flip based on insider sign (no trade_when).
    # When insider sentiment is positive -> long IV skew direction;
    # when negative -> opposite.
    ("g8_insider_directional",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "ts_decay_linear(if_else(ins > 0, -rank(iv), rank(iv)), 5)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G9 -- scale + winsorize: alternative normalization stack.
    ("g9_scale_winsorize",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "score = winsorize(zscore(iv), std=3) + 0.5 * winsorize(-zscore(supply), std=3);\n"
     "ts_decay_linear(scale(score), 5)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G10 -- vol-of-vol momentum: 5d change in 30d HV, ranked.
    ("g10_vov_momentum",
     "ch = ts_backfill(historical_volatility_30, 5) - "
     "ts_backfill(historical_volatility_30, 10);\n"
     "ts_decay_linear(-rank(ch), 10)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G11 -- rank-momentum: zscore of rank change in insider sentiment.
    ("g11_rank_momentum_insider",
     "raw = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "r = rank(raw);\n"
     "ch = r - ts_backfill(r, 5);\n"
     "ts_decay_linear(rank(ts_zscore(ch, 60)), 10)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # G12 -- max/min envelope: signed max(call_skew, put_skew) -- a
    # non-additive combination structurally different from a rank-sum.
    ("g12_envelope_iv",
     "call_skew = ts_backfill(implied_volatility_call_30 - implied_volatility_call_120, 5);\n"
     "put_skew  = ts_backfill(implied_volatility_put_30  - implied_volatility_put_120, 5);\n"
     "envelope = max(abs(call_skew), abs(put_skew)) * sign(call_skew - put_skew);\n"
     "ts_decay_linear(-rank(envelope), 10)",
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V6, 1):
        log.info(f"=== v6 [{i}/{len(CANDIDATES_V6)}] family={family} ===")
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
    eligible = [r for r in all_trials
                 if r.get("ok") and r.get("turnover", 1) < 0.25 and sc_pass(r)]
    eligible.sort(key=lambda r: r["sharpe"], reverse=True)

    print()
    print("=" * 130)
    print(f"All trials OK (rounds 1..7): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable (SH>1.25 AND TO<0.25 AND sc OK): {len(deliverable)}")
    # Only show round-6 (v6) trials so we can see what structures hit
    v6_results = [asdict(r) for r in results]
    print()
    print("ROUND 7 (v6) RESULTS — new structures/operators:")
    print(f"{'#':<4}{'family':<30}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v6_results if r.get('ok')],
                                   key=lambda x: x['sharpe'], reverse=True), 1):
        deliv = (r.get("ok") and r["sharpe"] > 1.25 and r["turnover"] < 0.25
                  and sc_pass(r))
        marker = "★" if deliv else " "
        sc = f"{r['self_corr']:+.3f}" if r.get("self_corr") is not None else "  -  "
        print(f"{marker}{i:<3}{r['family']:<30}{r['sharpe']:7.3f}{r['turnover']:7.3f}"
               f"{r['fitness']:7.3f} {r['checks_passed']:>2}/{r['checks_total']:<2}"
               f"{sc:>7} {r['alpha_id']:<10}")
    # Also show failures
    failures = [asdict(r) for r in results if not r.ok]
    if failures:
        print()
        print("FAILED:")
        for r in failures:
            print(f"   {r['family']:<30}  {r['error'][:120]}")
    print("=" * 130)

    with open(out_path, "w") as f:
        json.dump({"all_trials": all_trials}, f, indent=2)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
