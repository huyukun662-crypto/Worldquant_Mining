"""D0 mining on fundamental6 (clean Company Fundamental Data, 342
fields, delay=0).  Encodes the strongest documented equity anomalies
with cold operators.  NO option fields.

fundamental6 clean inputs (all delay=0, TOP3000):
  assets, liabilities, equity, income, operating_income, pretax_income,
  revenue, sales, cogs, cash, cashflow, cashflow_op, debt, capex,
  inventory, receivable, ebit, ebitda, retained_earnings, bookvalue_ps,
  return_assets, return_equity, enterprise_value, current_ratio,
  sales_growth, inventory_turnover, employee, depre_amort

Cold operators featured: group_rank, group_zscore, group_scale,
ts_av_diff, ts_rank, hump (correct named-param syntax), ts_delta.

Anomalies:
  gross profitability (Novy-Marx 2013) -- one of the most robust
  accruals (Sloan 1996)
  asset growth (Cooper-Gulen-Schill 2008)
  investment/capex (Titman-Wei-Xie 2004)
  ROA / ROE quality
  cashflow productivity
  composite quality
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (  # noqa: E402
    CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log,
)

BF = lambda f, d=250: f"ts_backfill({f}, {d})"

CANDIDATES: list[tuple[str, str, dict]] = [

    # 1. Gross profitability (Novy-Marx): (revenue - cogs)/assets, high=good
    ("f6_1_gross_profit",
     "gp = divide(ts_backfill(revenue, 250) - ts_backfill(cogs, 250), ts_backfill(assets, 250));\n"
     "group_rank(gp, subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 2. Accruals (Sloan): (income - cashflow_op)/assets, high=bad -> negate
    ("f6_2_accruals",
     "acc = divide(ts_backfill(income, 250) - ts_backfill(cashflow_op, 250), ts_backfill(assets, 250));\n"
     "-group_rank(acc, subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 3. Asset growth (Cooper): d(assets)/assets, high=bad -> negate
    ("f6_3_asset_growth",
     "g = divide(ts_delta(ts_backfill(assets, 250), 250), ts_backfill(assets, 250));\n"
     "-group_rank(g, subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 4. ROA quality (cold op group_zscore on return_assets)
    ("f6_4_roa",
     "group_zscore(ts_backfill(return_assets, 250), subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 5. Investment/capex anomaly: capex/assets, high=bad -> negate
    ("f6_5_investment",
     "inv = divide(ts_backfill(capex, 250), ts_backfill(assets, 250));\n"
     "-group_rank(inv, subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 6. Operating-cashflow productivity: cashflow_op/assets, high=good
    ("f6_6_cfo_productivity",
     "cfo = divide(ts_backfill(cashflow_op, 250), ts_backfill(assets, 250));\n"
     "group_rank(cfo, subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 7. Composite quality: GP + ROA + CFO - accruals - asset growth
    ("f6_7_composite_quality",
     "gp  = group_zscore(divide(ts_backfill(revenue,250)-ts_backfill(cogs,250), ts_backfill(assets,250)), subindustry);\n"
     "roa = group_zscore(ts_backfill(return_assets,250), subindustry);\n"
     "cfo = group_zscore(divide(ts_backfill(cashflow_op,250), ts_backfill(assets,250)), subindustry);\n"
     "acc = group_zscore(divide(ts_backfill(income,250)-ts_backfill(cashflow_op,250), ts_backfill(assets,250)), subindustry);\n"
     "g   = group_zscore(divide(ts_delta(ts_backfill(assets,250),250), ts_backfill(assets,250)), subindustry);\n"
     "gp + roa + cfo - acc - g",
     {"decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 8. Gross profitability with hump turnover-limiter (cold op, correct syntax)
    ("f6_8_gp_hump",
     "gp = group_zscore(divide(ts_backfill(revenue,250)-ts_backfill(cogs,250), ts_backfill(assets,250)), subindustry);\n"
     "hump(gp, hump=0.01)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 9. Earnings quality: ROA momentum minus accruals (cold ts_av_diff)
    ("f6_9_earnings_quality",
     "roa_mom = group_zscore(ts_av_diff(ts_backfill(return_assets,250), 250), subindustry);\n"
     "acc = group_zscore(divide(ts_backfill(income,250)-ts_backfill(cashflow_op,250), ts_backfill(assets,250)), subindustry);\n"
     "hump(roa_mom - acc, hump=0.02)",
     {"decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 10. Net debt issuance: d(debt)/assets, high=bad -> negate (cold ts_delta)
    ("f6_10_net_debt_issuance",
     "nd = divide(ts_delta(ts_backfill(debt,250),250), ts_backfill(assets,250));\n"
     "-group_rank(nd, subindustry)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 11. Quality + value combo: GP plus book/price proxy (cold group_scale)
    ("f6_11_quality_value",
     "gp = group_zscore(divide(ts_backfill(revenue,250)-ts_backfill(cogs,250), ts_backfill(assets,250)), subindustry);\n"
     "bv = group_zscore(divide(ts_backfill(bookvalue_ps,250), close), subindustry);\n"
     "hump(gp + bv, hump=0.02)",
     {"decay": 8, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 12. Composite quality, MARKET-neutralized variant
    ("f6_12_composite_market",
     "gp  = group_zscore(divide(ts_backfill(revenue,250)-ts_backfill(cogs,250), ts_backfill(assets,250)), market);\n"
     "roa = group_zscore(ts_backfill(return_assets,250), market);\n"
     "cfo = group_zscore(divide(ts_backfill(cashflow_op,250), ts_backfill(assets,250)), market);\n"
     "acc = group_zscore(divide(ts_backfill(income,250)-ts_backfill(cashflow_op,250), ts_backfill(assets,250)), market);\n"
     "hump(gp + roa + cfo - acc, hump=0.02)",
     {"decay": 8, "truncation": 0.05, "neutralization": "MARKET"}),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_D0_FUND6.json"
    results: list[CandidateResult] = []
    for i, (family, expr, settings) in enumerate(CANDIDATES, 1):
        s = dict(settings); s["delay"] = 0; s.setdefault("universe", "TOP3000")
        log.info(f"=== f6 [{i}/{len(CANDIDATES)}] family={family} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
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
            r.self_corr_peer = top.get("id"); r.self_corr_peer_sharpe = top.get("sharpe")
        log.info(f"   {r.alpha_id} self_corr={sc} ({st})")
    with open(out_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    def submittable(r):
        return r.ok and not any(c.get("result") == "FAIL" for c in r.checks)

    ok = sorted([r for r in results if r.ok], key=lambda r: r.sharpe, reverse=True)
    print("\n" + "=" * 120)
    print(f"fundamental6 D0 mining: {len(ok)}/{len(results)} OK")
    print(f"{'#':<4}{'family':<24}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'submit?':<7} alpha_id")
    for i, r in enumerate(ok, 1):
        sc = f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        print(f"{i:<4}{r.family:<24}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}"
               f"{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} "
               f"{'MAYBE' if submittable(r) else 'no':<7} {r.alpha_id}")
    for r in [r for r in results if not r.ok]:
        print(f"  FAIL {r.family:<22} {r.error[:100]}")
    print("=" * 120)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
