"""Round 12 (v11): act on round-11 leads.

Round-11 negative-SH alphas (signs need flipping):
  v10.2  pcr_curvature   SH=-0.65 -> flip
  v10.10 borrow_stack    SH=-0.73 -> flip

Round-11 positive-but-weak alphas (combine with proven framework):
  v10.9  shortfall x dispersion  SH=+0.70 -> add signed_power, multiply by IV
  v10.7  news_vwap_divergence    SH=+0.57 -> add IV+short
  v10.6  rp_nip_insider          SH=+0.31 -> add IV+short

Goal: push >=5 of these past SH>1.25 by combining the new
ingredients with the proven trade_when(news_gate, decay, -1) + IV+short
backbone.
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


CANDIDATES_V11: list[tuple[str, str, dict]] = [

    # === 1. pcr_curvature SIGN FLIPPED ============================
    ("v11_1_pcr_curvature_flipped",
     "curv = ts_backfill(pcr_oi_30 + pcr_oi_180 - 2 * pcr_oi_90, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(rank(curv), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 2. borrow_stack SIGN FLIPPED =============================
    ("v11_2_borrow_stack_flipped",
     "fee = ts_backfill(mdl177_5shortsentimentfactor_benchmark_fee, 30);\n"
     "util = ts_backfill(mdl177_5shortsentimentfactor_act_util, 30);\n"
     "dtc = ts_backfill(mdl177_5shortsentimentfactor_days_to_cover, 30);\n"
     "score = quantile(fee) + 0.5 * quantile(util) + 0.3 * quantile(dtc);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 3. shortfall x dispersion + signed_power amp =============
    ("v11_3_shortfall_disp_amp",
     "sf = ts_backfill(earnings_shortfall_metric, 30);\n"
     "ed = ts_backfill(fy1_eps_estimate_dispersion_2, 30);\n"
     "score = -quantile(sf) - 0.5 * quantile(ed);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score, 5), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 4. shortfall x dispersion + IV + short stack =============
    ("v11_4_shortfall_iv_short_stack",
     "sf = ts_backfill(earnings_shortfall_metric, 30);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness) - 0.3 * quantile(sf);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 5. news_vwap_divergence + IV + short stack ===============
    ("v11_5_vwap_iv_short_stack",
     "ratio = divide(ts_backfill(news_main_vwap, 5), ts_backfill(news_eod_vwap, 5));\n"
     "nz = ts_zscore(ratio, 60);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness) + 0.3 * quantile(nz);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 6. rp_nip + insider css/ess + IV stack ===================
    ("v11_6_nip_insider_iv_stack",
     "nip = ts_backfill(rp_nip_insider, 30);\n"
     "css = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.5 * quantile(css) + 0.3 * quantile(nip);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 7. HV regime + IV + short stack ==========================
    ("v11_7_hv_iv_short_stack",
     "hv30 = ts_backfill(historical_volatility_30, 5);\n"
     "hv120 = ts_backfill(historical_volatility_120, 5);\n"
     "hvr = -quantile(divide(hv30, hv120));\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness) + 0.3 * hvr;\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 8. pcr_curvature + IV + short stack ======================
    ("v11_8_pcr_curv_iv_short_stack",
     "curv = ts_backfill(pcr_oi_30 + pcr_oi_180 - 2 * pcr_oi_90, 5);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness) + 0.3 * quantile(curv);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 9. pcr_term + IV signed_power amp ========================
    ("v11_9_pcr_term_iv_amp",
     "pc = ts_backfill(pcr_oi_30 - pcr_oi_180, 5);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) - 0.5 * quantile(pc);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 10. news_atr + IV + short stack (gate by spike) ===========
    ("v11_10_natr_iv_short_stack",
     "atr = ts_backfill(news_atr_ratio, 10);\n"
     "atrz = ts_zscore(atr, 60);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = quantile(iv) + 0.5 * quantile(tightness) + 0.3 * quantile(-atrz);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V11, 1):
        log.info(f"=== v11 [{i}/{len(CANDIDATES_V11)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..12): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable: {len(deliverable)}")
    v11_results = [asdict(r) for r in results]
    print()
    print("ROUND 12 (v11) RESULTS:")
    print(f"{'#':<4}{'family':<36}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v11_results if r.get('ok')],
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
