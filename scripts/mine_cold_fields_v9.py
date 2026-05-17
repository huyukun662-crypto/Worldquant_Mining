"""Round 10: deliberately depart from the iv_skew + short_borrow pattern.

Everything that's been delivered so far uses some combination of
implied_volatility_call/put_*, mdl177_5shortsentimentfactor_lend_supply,
and rp_*_insider, all gated by news_pct_*.  This round forces NEW
field families AND new operator patterns:

NEW FIELDS:
  snt1_d1_netrecpercent       analyst net buy/sell recommendation
  snt1_d1_earningssurprise    earnings surprise score
  snt1_d1_earningsrevision    analyst earnings revision direction
  snt1_d1_buyrecpercent       % of analysts at buy
  news_main_vwap              VWAP during main news session
  news_eod_vwap               end-of-day VWAP
  news_pre_vwap               pre-market news VWAP
  news_short_interest         news-driven short interest
  historical_volatility_30/60 realized vol (for vol-regime gating)

NEW OPERATORS:
  tanh(x)            bounded non-linear, smooth alternative to signed_power
  s_log_1p(x)        log(1+|x|)*sign(x), magnitude compression
  group_max(x, g)    sector-relative ceiling
  ts_std_dev(x, w)   for volatility-of-X regime gating
  rank(A) - rank(B)  PAIR-trade direction (vs rank-sum)
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


CANDIDATES_V9: list[tuple[str, str, dict]] = [

    # ===== snt1_d1_* analyst signals (UNTOUCHED family) ==============

    # N1. Analyst net-rec momentum (5d change in net buy %).
    ("n1_net_rec_momentum",
     "nr = ts_backfill(snt1_d1_netrecpercent, 20);\n"
     "mom = ts_delta(nr, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(mom), 10), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # N2. Earnings surprise + revision combo (analyst flow direction).
    ("n2_earnings_flow",
     "es = ts_backfill(snt1_d1_earningssurprise, 30);\n"
     "er = ts_backfill(snt1_d1_earningsrevision, 30);\n"
     "score = quantile(es) + quantile(er);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 10), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # N3. Buy-recommendation extremes (contrarian: too-crowded -> short).
    ("n3_buy_rec_extreme",
     "br = ts_backfill(snt1_d1_buyrecpercent, 30);\n"
     "extreme = ts_zscore(br, 120);\n"
     "gate2 = ts_rank(abs(extreme), 60) > 0.90;\n"
     "trade_when(gate2, ts_decay_linear(-rank(extreme), 10), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== news VWAP intraday signals (UNTOUCHED family) =============

    # V1. News-main VWAP vs EOD VWAP (intraday news pricing impact).
    ("v1_news_main_vs_eod",
     "nm = ts_backfill(news_main_vwap, 5);\n"
     "ne = ts_backfill(news_eod_vwap, 5);\n"
     "ratio = (nm - ne) / (ne + 0.01);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(ratio), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # V2. Pre-news VWAP vs main: pre-news anticipation.
    ("v2_news_pre_vs_main",
     "np = ts_backfill(news_pre_vwap, 5);\n"
     "nm = ts_backfill(news_main_vwap, 5);\n"
     "anticipation = (np - nm) / (nm + 0.01);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(-rank(anticipation), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== Pair-trade direction (rank diff vs rank sum) ==============

    # P1. Long IV call rank, short IV put rank (one-sided vol signal).
    ("p1_iv_call_minus_put_pair",
     "callr = rank(ts_backfill(implied_volatility_call_60, 5));\n"
     "putr  = rank(ts_backfill(implied_volatility_put_60, 5));\n"
     "spread = callr - putr;\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(spread, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== Non-linear transforms (tanh, s_log_1p) ====================

    # T1. tanh on iv_x_short score (bounded smooth alt to signed_power).
    ("t1_tanh_iv_x_short",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = zscore(iv) + 0.5 * zscore(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(tanh(score), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # T2. s_log_1p magnitude compression on insider.
    ("t2_slog1p_insider",
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "compressed = s_log_1p(ins);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(compressed), 10), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== group_max sector-relative (NEW group op) ==================

    # G1. IV skew relative to sector ceiling (how far below the max).
    ("g1_group_max_iv",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "rel = iv - group_max(iv, sector);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(rel), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "NONE"}),

    # ===== ts_std_dev volatility-of-X gating =========================

    # R1. Vol-of-vol regime: only trade IV signal when HV vol is calm.
    ("r1_vol_regime_iv",
     "hv = ts_backfill(historical_volatility_30, 5);\n"
     "vov = ts_std_dev(hv, 30);\n"
     "calm_gate = ts_rank(vov, 60) < 0.30;\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness);\n"
     "trade_when(calm_gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== triple-stack of 3 cold signals from different datasets ====

    # X1. insider + iv_skew + news_main_vwap deviation (3 cold families).
    ("x1_triple_insider_iv_news",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "nvdev = ts_backfill((news_main_vwap - news_eod_vwap) / (news_eod_vwap + 0.01), 5);\n"
     "score = quantile(iv) + 0.5 * quantile(ins) + 0.5 * quantile(nvdev);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # ===== News-short-interest cold signal ===========================

    # NS1. News-driven short interest spike (different from mdl177 short).
    ("ns1_news_short_interest",
     "nsi = ts_backfill(news_short_interest, 10);\n"
     "spike = ts_zscore(nsi, 60);\n"
     "gate2 = ts_rank(spike, 60) > 0.85;\n"
     "trade_when(gate2, ts_decay_linear(-rank(spike), 5), -1)",
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V9, 1):
        log.info(f"=== v9 [{i}/{len(CANDIDATES_V9)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..10): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable: {len(deliverable)}")
    v9_results = [asdict(r) for r in results]
    print()
    print("ROUND 10 (v9) RESULTS:")
    print(f"{'#':<4}{'family':<32}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v9_results if r.get('ok')],
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
