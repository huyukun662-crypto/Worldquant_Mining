"""Round 15 (v14): OPTIONS + FUNDAMENTALS focus.

10 candidates split:

OPTIONS (untouched at delay=1):
  pcr_vol_*               Put/Call VOLUME ratio (we used only pcr_oi_*)
  forward_price_*         option-implied forward price
  call/put/option_breakeven_*  IV-implied strike breakeven

FUNDAMENTALS (mdl177_2 model factor families untouched):
  earningsqualityfactor    quality of earnings (accruals etc.)
  earningmomentumfactor400  EPS estimate momentum
  pricemomentumfactor      multi-horizon actual returns
  growthanalystmodel       analyst growth composite
  garpanalystmodel         Growth-at-Reasonable-Price
  valueanalystmodel        analyst value composite
  liquidityriskfactor      Altman-Z, liquidity risk
  managementqualityfactor  management/asset quality
  industryrrelativevaluefactor  industry-relative value
  historicalgrowthfactor   historical growth metrics
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


CANDIDATES_V14: list[tuple[str, str, dict]] = [

    # === OPTION (3) =================================================
    # 1. pcr_vol term structure (volume version of our winner pcr_oi)
    ("v14_1_pcr_vol_term",
     "pc = ts_backfill(pcr_vol_30 - pcr_vol_180, 5);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) - 0.5 * quantile(pc);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 2. forward_price premium relative to spot (option-implied drift)
    ("v14_2_forward_price_premium",
     "fp60  = ts_backfill(forward_price_60, 5);\n"
     "fp180 = ts_backfill(forward_price_180, 5);\n"
     "premium = divide(fp60, fp180);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(quantile(premium) - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 3. option_breakeven term structure (IV-implied strike distance)
    ("v14_3_option_breakeven_term",
     "be60  = ts_backfill(option_breakeven_60, 5);\n"
     "be180 = ts_backfill(option_breakeven_180, 5);\n"
     "spread = divide(be60, be180);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(quantile(-spread) - 0.5, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === FUNDAMENTAL (7) =============================================
    # 4. earnings quality composite (untouched family)
    ("v14_4_earnings_quality",
     "ch = ts_backfill(mdl177_2_earningsqualityfactor_chgsgasale, 30);\n"
     "co = ts_backfill(mdl177_2_earningsqualityfactor_cogsinvt, 30);\n"
     "dp = ts_backfill(mdl177_2_earningsqualityfactor_dpcapex, 30);\n"
     "score = -quantile(ch) - 0.5 * quantile(co) + 0.3 * quantile(dp);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 5. EPS estimate momentum (EPS revisions / coefficient-of-variation)
    ("v14_5_eps_momentum",
     "ch6 = ts_backfill(mdl177_2_earningmomentumfactor400_chg6mltg, 30);\n"
     "cv  = ts_backfill(mdl177_2_earningmomentumfactor400_cvfy1eps, 30);\n"
     "score = quantile(ch6) - 0.5 * quantile(cv);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 6. Price-momentum factor (multi-horizon returns from mdl177)
    ("v14_6_price_momentum_multi",
     "r12 = ts_backfill(mdl177_2_pricemomentumfactor_actrtn12m, 30);\n"
     "r1  = ts_backfill(mdl177_2_pricemomentumfactor_actrtn1m, 30);\n"
     "score = quantile(r12) - 0.5 * quantile(r1);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 7. GARP analyst model composite
    ("v14_7_garp_composite",
     "g = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(quantile(g) - 0.5, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 8. Liquidity risk: Altman-Z + accruals quality index
    ("v14_8_liquidity_risk",
     "alt = ts_backfill(mdl177_2_liquidityriskfactor_altmanz, 30);\n"
     "aqi = ts_backfill(mdl177_2_liquidityriskfactor_aqi, 30);\n"
     "score = quantile(alt) - 0.5 * quantile(aqi);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score - 0.25, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 9. Industry-relative value (composite of bp, fcfp, ebitdap)
    ("v14_9_industry_relvalue",
     "bp = ts_backfill(mdl177_2_industryrrelativevaluefactor_curindbp_, 30);\n"
     "fc = ts_backfill(mdl177_2_industryrrelativevaluefactor_curindfcfp_, 30);\n"
     "eb = ts_backfill(mdl177_2_industryrrelativevaluefactor_curindebitdap_, 30);\n"
     "score = quantile(bp) + quantile(fc) + quantile(eb);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(score / 3 - 0.5, 3), 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # 10. Combined: GARP + IV (fundamentals + options, no mdl177-short)
    ("v14_10_garp_plus_iv",
     "g = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);\n"
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "score = quantile(iv) + 0.5 * quantile(g);\n"
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V14, 1):
        log.info(f"=== v14 [{i}/{len(CANDIDATES_V14)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..15): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable: {len(deliverable)}")
    v14_results = [asdict(r) for r in results]
    print()
    print("ROUND 15 (v14) RESULTS  -- options + fundamentals:")
    print(f"{'#':<4}{'family':<32}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, r in enumerate(sorted([r for r in v14_results if r.get('ok')],
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
