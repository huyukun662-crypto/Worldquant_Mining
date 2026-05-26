"""D0 cold-fundamental factor mining (NO options, cold operators).

Per user spec:
  - delay=0 ONLY
  - cold fields: fn_* fundamentals (194 fields, delay=0, TOP1000) -- untouched
  - cold operators: ts_rank, group_zscore, hump, ts_av_diff, ts_delta,
                     group_scale, ts_step, last_diff_value, vec_avg
  - AVOID option fields entirely (implied_volatility, pcr_*, breakeven,
    forward_price, historical_volatility)
  - goal: pass submit check (all 8 IS checks PASS incl SELF_CORRELATION)

Each candidate encodes a documented fundamental anomaly with cold
operators:
  accruals (Sloan), asset growth (Cooper), SBC dilution, profit
  momentum, deferred-tax, capital aging, composite quality.

Fundamental data is quarterly -> naturally low turnover (good for the
HIGH_TURNOVER check); ts_backfill fills the gaps.
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

# Override FIXED_SETTINGS to delay=0 + TOP1000 (fn_ universe)
D0_FIXED = dict(FIXED_SETTINGS)
D0_FIXED.update({"delay": 0})


CANDIDATES_D0: list[tuple[str, str, dict]] = [

    # 1. Accruals anomaly (Sloan 1996): rising accrued liabilities =
    #    aggressive accounting -> underperform.  Cold ops: ts_av_diff,
    #    group_zscore, hump (turnover limiter).
    ("d0_1_accruals",
     "acc = ts_backfill(fn_accrued_liab_q, 120);\n"
     "sig = -group_zscore(ts_av_diff(acc, 250), subindustry);\n"
     "hump(sig, 0.01)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 2. Asset growth anomaly (Cooper et al 2008): PP&E growth ->
    #    overinvestment -> underperform.  Cold ops: ts_delta, group_rank.
    ("d0_2_asset_growth",
     "g = ts_delta(ts_backfill(fn_ppne_gross_q, 120), 250);\n"
     "-group_rank(g, subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 3. Share-based comp dilution: high SBC -> dilution -> underperform.
    #    Cold op: group_zscore + hump.
    ("d0_3_sbc_dilution",
     "sbc = ts_backfill(fn_allocated_share_based_compensation_expense_q, 120);\n"
     "hump(-group_zscore(sbc, subindustry), 0.02)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 4. Profit momentum: improving net profit -> outperform.
    #    Cold ops: ts_delta, group_rank.
    ("d0_4_profit_momentum",
     "p = ts_backfill(fn_profit_loss_q, 120);\n"
     "group_rank(ts_delta(p, 120), subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 5. Deferred-tax signal (cold op group_zscore on the fn_ version of
    #    the user's F2 field).
    ("d0_5_deferred_tax",
     "d = ts_backfill(fn_def_tax_assets_liab_net_q, 120);\n"
     "group_zscore(d, subindustry)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 6. Capital aging: high accumulated depreciation / PP&E gross =
    #    old asset base -> value-trap or renewal.  Cold ops: divide, ts_rank.
    ("d0_6_capital_aging",
     "dep = ts_backfill(fn_accum_depr_depletion_and_amortization_ppne_q, 120);\n"
     "ppne = ts_backfill(fn_ppne_gross_q, 120);\n"
     "ratio = divide(dep, ppne);\n"
     "group_rank(ts_rank(ratio, 250), subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 7. Composite quality: accruals + SBC + asset growth, all "bad"
    #    signals -> negate to long high-quality.  Cold op: group_zscore.
    ("d0_7_composite_quality",
     "acc = group_zscore(ts_av_diff(ts_backfill(fn_accrued_liab_q, 120), 250), subindustry);\n"
     "sbc = group_zscore(ts_backfill(fn_allocated_share_based_compensation_expense_q, 120), subindustry);\n"
     "g   = group_zscore(ts_delta(ts_backfill(fn_ppne_gross_q, 120), 250), subindustry);\n"
     "hump(-(acc + sbc + g), 0.02)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 8. Comprehensive-income surprise: income above its trailing
    #    average -> momentum.  Cold op: ts_av_diff.
    ("d0_8_income_surprise",
     "ci = ts_backfill(fn_comprehensive_income_net_of_tax_q, 120);\n"
     "group_rank(ts_av_diff(ci, 250), subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 9. Composite quality with news gate (news allowed, not option).
    ("d0_9_quality_news_gated",
     "acc = group_zscore(ts_av_diff(ts_backfill(fn_accrued_liab_q, 120), 250), subindustry);\n"
     "sbc = group_zscore(ts_backfill(fn_allocated_share_based_compensation_expense_q, 120), subindustry);\n"
     "g   = group_zscore(ts_delta(ts_backfill(fn_ppne_gross_q, 120), 250), subindustry);\n"
     "score = -(acc + sbc + g);\n"
     "gate = ts_rank(abs(ts_backfill(news_atr_ratio, 5)), 60) > 0.5;\n"
     "trade_when(gate, hump(score, 0.02), -1)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 10. Profit + accruals composite (earnings quality): high profit
    #     momentum BUT low accruals.  Cold ops: ts_delta, group_zscore.
    ("d0_10_earnings_quality",
     "p_mom = group_zscore(ts_delta(ts_backfill(fn_profit_loss_q, 120), 120), subindustry);\n"
     "acc   = group_zscore(ts_av_diff(ts_backfill(fn_accrued_liab_q, 120), 250), subindustry);\n"
     "hump(p_mom - acc, 0.02)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 11. Deferred-tax change momentum (cold ops: ts_delta + group_scale).
    ("d0_11_dtax_momentum",
     "d = ts_backfill(fn_def_tax_assets_liab_net_q, 120);\n"
     "group_scale(ts_delta(d, 120), subindustry)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 12. Equity-investment income (a niche P&L line) momentum.
    ("d0_12_equity_income",
     "ei = ts_backfill(fn_income_from_equity_investments_q, 120);\n"
     "group_rank(ts_av_diff(ei, 250), subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_D0_FUNDAMENTAL.json"
    results: list[CandidateResult] = []

    # Patch submit's settings dict by passing delay=0 explicitly in settings.
    for i, (family, expr, settings) in enumerate(CANDIDATES_D0, 1):
        s = dict(settings); s.setdefault("delay", 0)
        s.setdefault("universe", "TOP1000")  # fn_ fields are TOP1000
        log.info(f"=== d0 [{i}/{len(CANDIDATES_D0)}] family={family} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
        # submit() merges FIXED_SETTINGS (delay=1) then settings; our
        # settings override delay->0 + universe.
        res = submit(cm.session, family, expr, s)
        results.append(res)
        if not res.ok:
            log.warning(f"   FAILED: {res.error[:160]}")
        else:
            log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        with open(out_path, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

    log.info("=== pass 2: self-correlation ===")
    for r in results:
        if not r.ok or not r.alpha_id: continue
        sc, top, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=90)
        r.self_corr = sc
        if top:
            r.self_corr_peer = top.get("id")
            r.self_corr_peer_sharpe = top.get("sharpe")
        sc_s = f"{sc:.3f}" if sc is not None else "?"
        log.info(f"   {r.alpha_id} self_corr={sc_s} ({st})")
    with open(out_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    # A submittable alpha needs ALL gating checks to PASS.  We check the
    # raw checks array for any FAIL (SELF_CORRELATION may be PENDING).
    def submittable(r: CandidateResult) -> bool:
        if not r.ok: return False
        fails = [c for c in r.checks
                  if c.get("result") == "FAIL"]
        return len(fails) == 0

    ok = [r for r in results if r.ok]
    ok.sort(key=lambda r: r.sharpe, reverse=True)
    print()
    print("=" * 120)
    print(f"D0 fundamental mining: {len(ok)}/{len(results)} OK")
    print(f"{'#':<4}{'family':<24}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} "
           f"{'submit?':<8} alpha_id")
    for i, r in enumerate(ok, 1):
        sc = f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        sub = "MAYBE" if submittable(r) else "no"
        print(f"{i:<4}{r.family:<24}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}"
               f"{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {sub:<8} {r.alpha_id}")
    fails = [r for r in results if not r.ok]
    if fails:
        print("\nFAILED sims:")
        for r in fails:
            print(f"   {r.family:<24} {r.error[:110]}")
    print("=" * 120)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
