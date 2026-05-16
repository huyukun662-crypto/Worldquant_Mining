"""Round 13 (v12): produce mdl177-free alphas that are LOW-CORRELATED
with the existing 29 deliverables.

29 deliverables all use mdl177_5shortsentimentfactor_lend_supply as
the short-borrow tightness signal.  This round bans mdl177_* and
substitutes:
  - rp_*_insider           insider news flow
  - pcr_oi_*               option positioning
  - historical_volatility  realized vol
  - earnings_shortfall_*   fundamentals event
  - fy*_eps_dispersion     analyst uncertainty
  - news_pct_*             news activity (as signal, not just gate)
  - news_atr_*             news attention
  - news_*_vwap            intraday news pricing
  - snt1_d1_*              analyst sentiment

Also vary gates to avoid all 29 using news_pct_90/30 gate:
  - IV-based gate (ts_rank(abs(iv), 60) > 0.85)
  - HV regime gate (calm vol-of-vol)
  - no gate (daily trading)
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


CANDIDATES_V12: list[tuple[str, str, dict]] = [

    # === 1. Multi-tenor IV smile stack (pure IV, no mdl177) =========
    # 3 IV tenors stacked + signed_power amp + news_gate
    ("v12_1_multi_iv_tenor_stack",
     "iv30  = ts_backfill(implied_volatility_call_30  - implied_volatility_put_30,  5);\n"
     "iv60  = ts_backfill(implied_volatility_call_60  - implied_volatility_put_60,  5);\n"
     "iv120 = ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5);\n"
     "score = quantile(iv30) + quantile(iv60) + quantile(iv120);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score / 3 - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 2. PCR + IV + insider (replace short_borrow with insider) ===
    # 3-way stack -- different "stress" signal entirely
    ("v12_2_pcr_iv_insider_stack",
     "pc = ts_backfill(pcr_oi_30 - pcr_oi_180, 5);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = quantile(iv) - 0.5 * quantile(pc) + 0.3 * quantile(ins);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 3. HV term structure + IV-skew (pure vol, no mdl177) ========
    # HV30/HV120 + IV60 skew, no short signal
    ("v12_3_hv_iv_stack",
     "hv30  = ts_backfill(historical_volatility_30, 5);\n"
     "hv120 = ts_backfill(historical_volatility_120, 5);\n"
     "hvr   = -quantile(divide(hv30, hv120));\n"
     "iv    = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.5 * hvr;\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 4. Earnings shortfall + IV + dispersion (NO short_borrow) ===
    # 3-way fundamentals + options stack
    ("v12_4_shortfall_iv_disp_stack",
     "sf = ts_backfill(earnings_shortfall_metric, 30);\n"
     "ed = ts_backfill(fy1_eps_estimate_dispersion_2, 30);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) - 0.3 * quantile(sf) - 0.3 * quantile(ed);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 5. PCR-only + insider (NO IV, NO short, NO HV) ==============
    # Pure option-positioning + insider, very orthogonal
    ("v12_5_pcr_insider_only",
     "pc = ts_backfill(pcr_oi_30 - pcr_oi_180, 5);\n"
     "curv = ts_backfill(pcr_oi_30 + pcr_oi_180 - 2 * pcr_oi_90, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = -quantile(pc) + 0.3 * quantile(curv) + 0.5 * quantile(ins);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 6. News attention + insider (NO IV at all) ==================
    # Pure news + insider, very different from IV-based winners
    ("v12_6_news_insider_only",
     "atr = ts_backfill(news_atr_ratio, 10);\n"
     "atrz = ts_zscore(atr, 60);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = quantile(-atrz) + 0.5 * quantile(ins);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 7. IV with IV-based gate (no news_pct) ======================
    # Same IV signal but different gate -> different alpha
    ("v12_7_iv_iv_gated_amp",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "iv_gate = ts_rank(abs(iv), 60) > 0.90;\n"
     "trade_when(iv_gate, ts_decay_linear(signed_power(rank(iv) - 0.5, 5), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 8. PCR + IV with HV calm-regime gate ========================
    # Vol-regime gating + 2-way PCR/IV signal (no mdl177)
    ("v12_8_pcr_iv_vol_calm",
     "hv = ts_backfill(historical_volatility_30, 5);\n"
     "vov = ts_std_dev(hv, 30);\n"
     "calm_gate = ts_rank(vov, 60) < 0.30;\n"
     "pc = ts_backfill(pcr_oi_30 - pcr_oi_180, 5);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) - 0.5 * quantile(pc);\n"
     "trade_when(calm_gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 9. IV smile + IV term structure (pure IV multi-aspect) ======
    # Smile (call-put) + Term (30-120) -> different IV dimensions
    ("v12_9_iv_smile_x_term",
     "smile = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "term_call = ts_backfill(implied_volatility_call_30 - implied_volatility_call_120, 5);\n"
     "term_put  = ts_backfill(implied_volatility_put_30  - implied_volatility_put_120, 5);\n"
     "score = quantile(smile) + 0.3 * quantile(term_call) + 0.3 * quantile(term_put);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === 10. snt1_d1 earnings + IV (analyst signal with IV backbone) =
    # Use earnings_surprise + IV (no mdl177, no insider)
    ("v12_10_snt1_iv_stack",
     "es = ts_backfill(snt1_d1_earningssurprise, 20);\n"
     "er = ts_backfill(snt1_d1_earningsrevision, 20);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.3 * quantile(es) + 0.3 * quantile(er);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)",
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V12, 1):
        log.info(f"=== v12 [{i}/{len(CANDIDATES_V12)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..13): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable: {len(deliverable)}")
    v12_results = [asdict(r) for r in results]
    print()
    print("ROUND 13 (v12) RESULTS  -- mdl177-free, low-correlation candidates:")
    print(f"{'#':<4}{'family':<36}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v12_results if r.get('ok')],
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
