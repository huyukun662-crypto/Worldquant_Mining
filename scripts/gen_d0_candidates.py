"""Generate delay-0 candidate expressions from COLD fields x COLD operators.

No Alpha101 / classical-template reuse. Avoids the `option` category and
the crowded PV set. Emits one expression per line, with optional
`| neutralization=... decay=...` setting overrides.
"""
from __future__ import annotations
import sys

# --- COLD news12 fields (delay0, userCount 1-49, cov ~0.92-0.97) ----------
NEWS_DRIFT = ["news_pct_30sec", "news_pct_1min", "news_pct_30min",
              "news_pct_60min", "news_pct_90min"]
NEWS_EXTREME = ["news_max_up_ret", "news_max_dn_ret"]
NEWS_OTHER = {
    "news_short_interest": "short",      # contrarian-ish
    "news_vol_stddev": "volz",           # abnormal volume -> reversal
    "news_indx_perf": "relstr",          # stock vs index
    "news_pe_ratio": "value",            # low PE = cheap
    "news_eps_actual": "eps",
    "news_atr14": "vol",
    "news_high_exc_stddev": "hi",
    "news_low_exc_stddev": "lo",
}
# --- COLD fundamental fields (delay0, userCount 0-1, need backfill 250) ---
FUND = ["fnd6_spced", "fn_repayments_of_debt_q",
        "fn_proceeds_from_issuance_of_debt_a", "fn_def_income_tax_expense_q"]

GROUPS = ["subindustry", "sector"]


def out(expr, **ov):
    s = " ".join(f"{k}={v}" for k, v in ov.items())
    print(f"{expr} | {s}" if s else expr)


def main():
    # 1. News post-event drift: cross-sectional group rank, both signs.
    for f in NEWS_DRIFT:
        out(f"group_rank(ts_backfill({f}, 5), subindustry)")
        out(f"-group_rank(ts_backfill({f}, 5), subindustry)")          # reversal
    # 2. Drift with hump (turnover control) + sector neutralize
    for f in NEWS_DRIFT[:3]:
        out(f"hump(group_neutralize(ts_backfill({f}, 5), sector), hump=0.01)")
    # 3. ts_av_diff (demeaned) momentum on drift
    for f in ["news_pct_60min", "news_pct_30min"]:
        out(f"group_rank(ts_av_diff(ts_backfill({f}, 10), 5), subindustry)")
    # 4. Abnormal-volume reversal
    out("-group_rank(ts_backfill(news_vol_stddev, 5), subindustry)")
    out("-rank(ts_av_diff(ts_backfill(news_vol_stddev, 10), 5))")
    # 5. Short interest pressure (both signs)
    out("-group_rank(ts_backfill(news_short_interest, 22), sector)")
    out("group_rank(ts_backfill(news_short_interest, 22), sector)")
    out("hump(group_neutralize(ts_backfill(news_short_interest, 22), sector), hump=0.02)")
    # 6. Relative strength vs index
    out("group_rank(ts_backfill(news_indx_perf, 10), subindustry)")
    out("-group_rank(ts_backfill(news_indx_perf, 10), subindustry)")
    # 7. Valuation: cheap=long -> negate PE rank
    out("-group_rank(ts_backfill(news_pe_ratio, 60), sector)")
    out("-group_zscore(ts_backfill(news_pe_ratio, 60), sector)")
    # 8. EPS surprise momentum
    out("group_rank(ts_delta(ts_backfill(news_eps_actual, 250), 60), sector)")
    # 9. Intraday extreme reversal (max up -> short)
    out("-group_rank(ts_backfill(news_max_up_ret, 5), subindustry)")
    out("group_rank(ts_backfill(news_max_dn_ret, 5), subindustry)")
    # 10. trade_when conditional: trade only on news days
    out("trade_when(news_tot_ticks > 0, -group_rank(ts_backfill(news_vol_stddev, 5), subindustry), -1)")
    out("trade_when(news_tot_ticks > 0, group_rank(ts_backfill(news_pct_60min, 5), sector), -1)")
    # 11. High/low exc stddev spread (intraday range signal)
    out("group_rank(subtract(ts_backfill(news_high_exc_stddev,5), ts_backfill(news_low_exc_stddev,5)), subindustry)")
    # 12. jump_decay smoothed drift
    out("group_rank(jump_decay(ts_backfill(news_pct_60min, 5), 5), subindustry)")
    # 13. Fundamental cold fields, backfilled + group ranked
    for f in FUND:
        out(f"group_rank(ts_backfill({f}, 250), sector)")
    # 14. signed_power to sharpen tails on drift
    out("group_rank(signed_power(ts_backfill(news_pct_60min, 5), 0.5), subindustry)")
    # 15. winsorize then zscore on volume z
    out("-zscore(winsorize(ts_backfill(news_vol_stddev, 5), std=4))")
    # --- a few decay / universe variants of the most promising structure ---
    out("group_rank(ts_backfill(news_pct_60min, 5), subindustry)", decay=8)
    out("group_rank(ts_backfill(news_pct_60min, 5), subindustry)", universe="TOP1000")


if __name__ == "__main__":
    main()
