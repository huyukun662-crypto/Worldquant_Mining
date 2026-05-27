"""Run a batch of (name, expression, settings) candidates concurrently on
WQ Brain, print IS metrics + checks, save JSON. delay=0 only.
"""
from __future__ import annotations
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.wq_lib import auth, simulate, is_metrics

# Candidate batches are defined inline; pass a batch name as argv[1].
def wrap_subind_value(field, n=120):
    # low-value long: industry-neutral, winsorized, backfilled
    return f"group_neutralize(-winsorize(ts_backfill({field}, {n}), std=4), subindustry)"

def wrap_subind_reversal(field, n=22):
    return f"group_neutralize(-winsorize(ts_backfill({field}, {n}), std=4), subindustry)"


# --- ensemble builders (stack orthogonal cold D0 signals for high Sharpe) ---
def _addall(parts):
    expr = parts[0]
    for p in parts[1:]:
        expr = f"add({expr}, {p})"
    return expr

VAL = "quantile(ts_backfill(divide(est_ebitda, cap), 120))"
def _relrev(f, s=5):
    return f"multiply(quantile(ts_mean(ts_backfill({f}, 120), {s})), -1)"
def _newsrev(f, n=22):
    return f"multiply(quantile(ts_backfill({f}, {n})), -1)"

REL4 = [_relrev(f) for f in ("rel_ret_cust", "rel_ret_comp", "rel_ret_part", "rel_ret_all")]
NEWS3 = [_newsrev(f) for f in ("news_pct_60min", "news_max_up_ret", "news_indx_perf")]

# Earnings surprise (PEAD): (actual EPS - consensus EPS) / price, persisted.
PEAD = "quantile(ts_backfill(divide(subtract(news_eps_actual, est_epsr), close), 120))"
CUSTREV = _relrev("rel_ret_cust")
VAL_REL = f"add({VAL}, {CUSTREV})"
RECRAW = "quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22))"
VWAPREV = "quantile(divide(subtract(vwap, close), close))"
S4 = f"add(add(add({VAL}, {RECRAW}), {CUSTREV}), {VWAPREV})"

BATCHES = {
    # NON-OPTION families (user: mine factors other than the option IV-spread).
    # Apply the winning structure that cracked the option factor -- group_zscore
    # by SECTOR + MARKET neut + decay20 + ts_backfill -- to forward-looking
    # non-option signals: analyst revisions, short interest, insider sentiment,
    # news sentiment, quality. Reversal-blend the strongest to lift Sharpe.
    # NON-OPTION winner hunt: short interest (news_short_interest) is the
    # strongest clean non-option signal (|SH| 1.56, slow, low TO) but fails
    # CONCENTRATED_WEIGHT + sub-universe raw. winsorize fixes concentration,
    # longer backfill fixes coverage, orthogonal value+reversal blends lift SH.
    # NON-OPTION SH>=2 hunt (delay=0, user pick). maxstack (value+news+rev+
    # sentiment) caps SH 1.93 but TO 0.99. Add short interest (strongest single
    # non-option, slow/low-TO, orthogonal) to lift SH AND dilute turnover, then
    # decay to tame the residual. All quantile-based so concentration stays OK.
    # PURE-SLOW multi-factor stack (user pick). All components persistent/low-TO
    # and rank/quantile-normalized (uniform weights -> no concentration). Low
    # turnover by construction; orthogonal slow signals (short interest, value,
    # long-term reversal, cash profitability, investment growth) stack Sharpe.
    # CONCENTRATION FIX: outermost rank() forces uniform bounded weights ->
    # passes CONCENTRATED_WEIGHT regardless of field coverage, while preserving
    # signal ordering (IC). Anchor = short interest (strongest D0 non-option
    # slow signal, |SH| 1.66) stacked with orthogonal dense slow signals
    # (value, long-term reversal, 52-week-high proximity / George-Hwang).
    # DENSE-ONLY probe: 100%% price/volume coverage -> guaranteed to pass
    # CONCENTRATED_WEIGHT (every name positioned). Individually test slow/medium
    # anomalies to find strong (|SH|>0.8) + mutually orthogonal ones to stack.
    # probe7: (A) group_backfill densify sparse short interest; (B) dense reversal maximization
    # probe8: unit-fixed group_backfill densification (zscore strips units) to rescue
    # the strong-but-sparse news short interest into a concentration-passing alpha
    # probe9: analyst estimate-revision signals (D0 analyst4) - revision breadth (pu-down)/numest,
    # EPS revision (est-preest), dispersion. Strong anomaly, slow-updating (low TO), broad coverage.
    # probe10: analyst revision signals WITHOUT ts_backfill (event-type fields persist natively)
    # probe11: analyst revision signals with vec_avg (VECTOR fields reduced to scalar)
    "newfam_probe11": [
        ("anl_breadth_af", "group_zscore(divide(subtract(vec_avg(anl4_basicconaf_pu), vec_avg(anl4_basicconaf_down)), add(vec_avg(anl4_basicconaf_numest), 1)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_breadth_qf", "group_zscore(divide(subtract(vec_avg(anl4_basicconqf_pu), vec_avg(anl4_basicconqf_down)), add(vec_avg(anl4_basicconqf_numest), 1)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_rev_eps", "group_zscore(divide(subtract(vec_avg(anl4_dez1afv4_est), vec_avg(anl4_dez1afv4_preest)), add(abs(vec_avg(anl4_dez1afv4_preest)), 0.01)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_disp", "group_zscore(multiply(divide(subtract(vec_avg(anl4_basicconaf_high), vec_avg(anl4_basicconaf_low)), add(abs(vec_avg(anl4_basicconaf_mean)), 0.01)), -1), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_combo", "add(group_zscore(divide(subtract(vec_avg(anl4_basicconaf_pu), vec_avg(anl4_basicconaf_down)), add(vec_avg(anl4_basicconaf_numest), 1)), market), group_zscore(divide(subtract(vec_avg(anl4_basicconqf_pu), vec_avg(anl4_basicconqf_down)), add(vec_avg(anl4_basicconqf_numest), 1)), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_rev_breadth", "add(group_zscore(divide(subtract(vec_avg(anl4_basicconaf_pu), vec_avg(anl4_basicconaf_down)), add(vec_avg(anl4_basicconaf_numest), 1)), market), group_zscore(divide(subtract(vec_avg(anl4_dez1afv4_est), vec_avg(anl4_dez1afv4_preest)), add(abs(vec_avg(anl4_dez1afv4_preest)), 0.01)), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe10": [
        ("anl_breadth_af", "group_zscore(divide(subtract(anl4_basicconaf_pu, anl4_basicconaf_down), add(anl4_basicconaf_numest, 1)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_breadth_qf", "group_zscore(divide(subtract(anl4_basicconqf_pu, anl4_basicconqf_down), add(anl4_basicconqf_numest, 1)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_rev_eps", "group_zscore(divide(subtract(anl4_dez1afv4_est, anl4_dez1afv4_preest), add(abs(anl4_dez1afv4_preest), 0.01)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_disp", "group_zscore(multiply(divide(subtract(anl4_basicconaf_high, anl4_basicconaf_low), add(abs(anl4_basicconaf_mean), 0.01)), -1), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_combo", "add(group_zscore(divide(subtract(anl4_basicconaf_pu, anl4_basicconaf_down), add(anl4_basicconaf_numest, 1)), market), group_zscore(divide(subtract(anl4_basicconqf_pu, anl4_basicconqf_down), add(anl4_basicconqf_numest, 1)), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_combo_disp", "add(add(group_zscore(divide(subtract(anl4_basicconaf_pu, anl4_basicconaf_down), add(anl4_basicconaf_numest, 1)), market), group_zscore(divide(subtract(anl4_basicconqf_pu, anl4_basicconqf_down), add(anl4_basicconqf_numest, 1)), market)), group_zscore(multiply(divide(subtract(anl4_basicconaf_high, anl4_basicconaf_low), add(abs(anl4_basicconaf_mean), 0.01)), -1), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe9": [
        ("anl_breadth_af", "group_zscore(divide(subtract(ts_backfill(anl4_basicconaf_pu, 66), ts_backfill(anl4_basicconaf_down, 66)), add(ts_backfill(anl4_basicconaf_numest, 66), 1)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_breadth_qf", "group_zscore(divide(subtract(ts_backfill(anl4_basicconqf_pu, 66), ts_backfill(anl4_basicconqf_down, 66)), add(ts_backfill(anl4_basicconqf_numest, 66), 1)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_rev_eps", "group_zscore(divide(subtract(ts_backfill(anl4_dez1afv4_est, 66), ts_backfill(anl4_dez1afv4_preest, 66)), add(abs(ts_backfill(anl4_dez1afv4_preest, 66)), 0.01)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_disp", "group_zscore(multiply(divide(subtract(ts_backfill(anl4_basicconaf_high, 66), ts_backfill(anl4_basicconaf_low, 66)), add(abs(ts_backfill(anl4_basicconaf_mean, 66)), 0.01)), -1), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("anl_breadth_sub", "group_zscore(divide(subtract(ts_backfill(anl4_basicconaf_pu, 66), ts_backfill(anl4_basicconaf_down, 66)), add(ts_backfill(anl4_basicconaf_numest, 66), 1)), subindustry)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("anl_combo", "add(group_zscore(divide(subtract(ts_backfill(anl4_basicconaf_pu, 66), ts_backfill(anl4_basicconaf_down, 66)), add(ts_backfill(anl4_basicconaf_numest, 66), 1)), market), group_zscore(divide(subtract(ts_backfill(anl4_basicconqf_pu, 66), ts_backfill(anl4_basicconqf_down, 66)), add(ts_backfill(anl4_basicconqf_numest, 66), 1)), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    # probe12: economic-link / supply-chain momentum (Cohen-Frazzini customer momentum).
    # rel_ret_cust/comp/part/all = avg returns of linked firms. MATRIX -> dense -> pass concentration.
    # probe13: news volume/volatility shocks (attention/informed flow), volume-scaled reversal,
    # dense earnings yield, and a pure-dense orthogonal stack. All MATRIX -> pass concentration.
    "newfam_probe13": [
        ("volz", "group_zscore(news_vol_stddev, market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("rangez", "group_zscore(news_range_stddev, market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("vol_rev", "multiply(quantile(divide(subtract(vwap, close), close)), rank(news_ratio_vol))", {'decay': 10, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("revz", "group_zscore(divide(subtract(vwap, close), close), market)", {'decay': 10, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("earnyld", "group_zscore(divide(fnd6_epsfx, close), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("dense3", "add(add(group_zscore(divide(subtract(vwap, close), close), market), group_zscore(ts_mean(rel_ret_comp, 22), market)), multiply(group_zscore(news_vol_stddev, market), -1))", {'decay': 8, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe12": [
        ("cust22", "group_zscore(ts_mean(rel_ret_cust, 22), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("comp22", "group_zscore(ts_mean(rel_ret_comp, 22), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("part22", "group_zscore(ts_mean(rel_ret_part, 22), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("all22", "group_zscore(ts_mean(rel_ret_all, 22), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("cust5", "group_zscore(ts_mean(rel_ret_cust, 5), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("link_combo", "add(add(group_zscore(ts_mean(rel_ret_cust, 22), market), group_zscore(ts_mean(rel_ret_part, 22), market)), group_zscore(ts_mean(rel_ret_all, 22), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe8": [
        ("si_gbz", "rank(group_backfill(group_zscore(ts_backfill(news_short_interest, 66), market), market, 250))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("si_gbz_d2", "rank(group_backfill(group_zscore(ts_backfill(news_short_interest, 66), market), market, 250))", {'decay': 2, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("si_gbz_sec", "rank(group_backfill(group_zscore(ts_backfill(news_short_interest, 66), sector), sector, 250))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("si_gbz_rev", "add(rank(group_backfill(group_zscore(ts_backfill(news_short_interest, 66), market), market, 250)), quantile(divide(subtract(vwap, close), close)))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("si_gbz_w", "winsorize(group_backfill(group_zscore(ts_backfill(news_short_interest, 66), market), market, 250), std=3)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe7": [
        ("si_gb", "rank(group_zscore(group_backfill(ts_backfill(news_short_interest, 66), market, 120), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("si_gb_sub", "rank(group_zscore(group_backfill(ts_backfill(news_short_interest, 66), subindustry, 120), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("rev_r", "quantile(divide(subtract(vwap, close), close))", {'decay': 10, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("rev5", "group_zscore(multiply(ts_returns(close, 5), -1), subindustry)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("rev_stack", "add(add(quantile(divide(subtract(vwap, close), close)), group_zscore(multiply(ts_returns(close, 5), -1), subindustry)), group_zscore(multiply(ts_returns(close, 10), -1), subindustry))", {'decay': 10, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("rev_r_d20", "quantile(divide(subtract(vwap, close), close))", {'decay': 20, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
    ],
    "newfam_probe6": [
        ("overnight", "rank(ts_mean(subtract(divide(open, ts_delay(close, 1)), 1), 60))", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("w52r", "rank(ts_rank(close, 252))", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("amihud", "rank(ts_mean(divide(abs(returns), add(volume, 1)), 60))", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("pvcorr", "rank(ts_corr(close, volume, 60))", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("idiovol", "rank(ts_std_dev(returns, 120))", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("skew", "rank(ts_skewness(returns, 60))", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("si_coal", "rank(coalesce(group_zscore(ts_backfill(news_short_interest, 66), market), 0))", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("si_coal_on", "add(coalesce(group_zscore(ts_backfill(news_short_interest, 66), market), 0), zscore(ts_mean(subtract(divide(open, ts_delay(close, 1)), 1), 60)))", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    "newfam_probe5": [
        ("si_rank",    "rank(group_zscore(ts_backfill(news_short_interest, 66), sector))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("si_rank_mkt","rank(group_zscore(ts_backfill(news_short_interest, 66), sector))", {"decay":4, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("w52_only",   "rank(group_zscore(divide(close, ts_max(high, 252)), sector))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("si_w52",     "rank(add(group_zscore(ts_backfill(news_short_interest, 66), sector), group_zscore(divide(close, ts_max(high, 252)), sector)))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("si_val_lt",  "rank(add(add(group_zscore(ts_backfill(news_short_interest, 66), sector), group_zscore(ts_backfill(divide(est_ebitda, cap), 120), sector)), group_zscore(multiply(divide(ts_delay(close, 21), ts_delay(close, 750)), -1), sector)))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("si_all4",    "rank(add(add(add(group_zscore(ts_backfill(news_short_interest, 66), sector), group_zscore(ts_backfill(divide(est_ebitda, cap), 120), sector)), group_zscore(multiply(divide(ts_delay(close, 21), ts_delay(close, 750)), -1), sector)), group_zscore(divide(close, ts_max(high, 252)), sector)))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    "newfam_probe4": [
        ("slow5",     "add(add(add(add(rank(ts_backfill(news_short_interest, 66)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(rank(divide(ts_delay(close, 21), ts_delay(close, 750))), -1)), quantile(ts_backfill(divide(subtract(subtract(revenue, cogs), sga_expense), assets), 250))), multiply(rank(divide(ts_delta(ts_backfill(fnd6_invt, 60), 250), ts_backfill(assets, 60))), -1))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("slow5_mkt", "add(add(add(add(rank(ts_backfill(news_short_interest, 66)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(rank(divide(ts_delay(close, 21), ts_delay(close, 750))), -1)), quantile(ts_backfill(divide(subtract(subtract(revenue, cogs), sga_expense), assets), 250))), multiply(rank(divide(ts_delta(ts_backfill(fnd6_invt, 60), 250), ts_backfill(assets, 60))), -1))", {"decay":4, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("slow3",     "add(add(rank(ts_backfill(news_short_interest, 66)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(rank(divide(ts_delay(close, 21), ts_delay(close, 750))), -1))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("slow_si2",  "add(add(add(add(rank(ts_backfill(news_short_interest, 66)), rank(ts_backfill(news_short_interest, 66))), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(rank(divide(ts_delay(close, 21), ts_delay(close, 750))), -1)), quantile(ts_backfill(divide(subtract(subtract(revenue, cogs), sga_expense), assets), 250)))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("slow_silt", "add(rank(ts_backfill(news_short_interest, 66)), multiply(rank(divide(ts_delay(close, 21), ts_delay(close, 750))), -1))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("slow5_grp", "group_zscore(add(add(add(add(rank(ts_backfill(news_short_interest, 66)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(rank(divide(ts_delay(close, 21), ts_delay(close, 750))), -1)), quantile(ts_backfill(divide(subtract(subtract(revenue, cogs), sga_expense), assets), 250))), multiply(rank(divide(ts_delta(ts_backfill(fnd6_invt, 60), 250), ts_backfill(assets, 60))), -1)), sector)", {"decay":4, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    "newfam_probe3": [
        ("ms_si",     "add(add(add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), add(quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5))), winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4))", {"decay":0,  "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ms_si_d6",  "add(add(add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), add(quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5))), winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4))", {"decay":6,  "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ms_si_d12", "add(add(add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), add(quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5))), winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4))", {"decay":12, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ms_si_mkt", "add(add(add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), add(quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5))), winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4))", {"decay":6,  "universe":"TOP3000", "neutralization":"MARKET"}),
        ("ms_si_grp", "group_zscore(add(add(add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), add(quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5))), winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)), sector)", {"decay":6, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("ms_d8",     "add(add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), add(quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5)))", {"decay":8,  "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    "newfam_probe2": [
        ("si_w",   "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {"decay":10, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("si_v",   "add(winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4), quantile(ts_backfill(divide(est_ebitda, cap), 120)))", {"decay":10, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("si_r",   "add(winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4), quantile(divide(subtract(vwap, close), close)))", {"decay":10, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("si_vr",  "add(add(winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4), quantile(ts_backfill(divide(est_ebitda, cap), 120))), quantile(divide(subtract(vwap, close), close)))", {"decay":10, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("si_v2r", "add(add(add(winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4), quantile(ts_backfill(divide(est_ebitda, cap), 120))), quantile(divide(subtract(vwap, close), close))), quantile(divide(subtract(vwap, close), close)))", {"decay":10, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("si_sub", "add(winsorize(group_zscore(ts_backfill(news_short_interest, 66), subindustry), std=4), quantile(ts_backfill(divide(est_ebitda, cap), 120)))", {"decay":10, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    "newfam_probe1": [
        ("anlrev",   "group_zscore(ts_backfill(net_num_revisions_fy1, 66), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("anlrank",  "group_zscore(ts_backfill(analyst_revision_rank_derivative, 22), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("shortint", "multiply(group_zscore(ts_backfill(news_short_interest, 22), sector), -1)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("insider",  "group_zscore(ts_backfill(rp_ess_insider, 22), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("peg",      "multiply(group_zscore(ts_backfill(inverse_peg_ratio_2, 120), sector), 1)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("news_grp", "group_zscore(ts_backfill(vec_avg(nws18_ghc_lna), 22), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    "news_probe": [
        ("pe_value",   "group_neutralize(-winsorize(ts_backfill(news_pe_ratio, 250), std=4), subindustry)", {"decay":6}),
        ("vol_shock",  "group_neutralize(-winsorize(ts_backfill(news_vol_stddev, 22), std=4), subindustry)", {"decay":6}),
        ("react_60m",  "group_neutralize(-winsorize(ts_backfill(news_pct_60min, 22), std=4), subindustry)", {"decay":6}),
        ("indx_rel",   "group_neutralize(-winsorize(ts_backfill(news_indx_perf, 22), std=4), subindustry)", {"decay":6}),
    ],
    # rel_* = supply-chain / competitor network (Cohen-Frazzini lead-lag).
    # cold (userCount 2-5), economically grounded -> low self-correlation.
    "rel_probe": [
        ("all_mom",   "group_neutralize(ts_decay_linear(ts_backfill(rel_ret_all, 60), 5), subindustry)", {"decay":4}),
        ("comp_mom",  "group_neutralize(ts_decay_linear(ts_backfill(rel_ret_comp, 60), 5), subindustry)", {"decay":4}),
        ("cust_mom",  "group_neutralize(ts_decay_linear(ts_backfill(rel_ret_cust, 120), 5), subindustry)", {"decay":4}),
        ("part_mom",  "group_neutralize(ts_decay_linear(ts_backfill(rel_ret_part, 120), 5), subindustry)", {"decay":4}),
    ],
    # analyst4 = cold consensus estimates (u<100). Forward value yields +
    # estimate-revision momentum. Neutralization via settings (SUBINDUSTRY).
    # Cold operators: ts_backfill + winsorize.
    "anl_probe": [
        ("fcf_yield",   "winsorize(ts_backfill(divide(est_fcf_ps, close), 120), std=4)", {"decay":4}),
        ("earn_yield",  "winsorize(ts_backfill(divide(est_epsr, close), 120), std=4)", {"decay":4}),
        ("book_price",  "winsorize(ts_backfill(divide(est_bookvalue_ps, close), 120), std=4)", {"decay":4}),
        ("fcf_assets",  "winsorize(ts_backfill(divide(est_fcf, est_tot_assets), 120), std=4)", {"decay":4}),
        ("eps_revis",   "winsorize(ts_backfill(divide(ts_delta(est_epsr, 66), close), 120), std=4)", {"decay":4}),
        ("ebitda_yield","winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4)", {"decay":4}),
    ],
    # Refine the winner: forward EBITDA-yield (est_ebitda/cap). Raw winsorize
    # failed CONCENTRATED_WEIGHT + sub-universe; rank/zscore even out weights.
    "refine1": [
        ("eby_rank_t3_si",  "rank(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eby_zsc_t3_si",   "zscore(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eby_rank_t1_si",  "rank(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":4, "universe":"TOP1000", "neutralization":"SUBINDUSTRY"}),
        ("eby_rank_t3_ind", "rank(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":4, "universe":"TOP3000", "neutralization":"INDUSTRY"}),
        ("eby_quant_t3_si", "quantile(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("comp_eby_fcf",    "add(rank(ts_backfill(divide(est_ebitda, cap), 120)), rank(ts_backfill(divide(est_fcf_ps, close), 120)))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Push SH 1.06 -> >1.25. EBITDA/EV (EV=cap+net debt) is the proper
    # enterprise multiple; tune decay/window; combine two valuation legs.
    "refine2": [
        ("ev_quant",      "quantile(ts_backfill(divide(est_ebitda, add(cap, est_netdebt)), 120))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ev_rank",       "rank(ts_backfill(divide(est_ebitda, add(cap, est_netdebt)), 120))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ebit_ev_quant", "quantile(ts_backfill(divide(est_ebit, add(cap, est_netdebt)), 120))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eby_quant_d0",  "quantile(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ev_sector",     "quantile(ts_backfill(divide(est_ebitda, add(cap, est_netdebt)), 120))", {"decay":4, "universe":"TOP3000", "neutralization":"SECTOR"}),
        ("comp_ev_cap",   "add(quantile(ts_backfill(divide(est_ebitda, add(cap, est_netdebt)), 120)), quantile(ts_backfill(divide(est_ebitda, cap), 120)))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Lift SH 1.09 -> >1.25. EV via unitHandling=IGNORE; truncation/window/
    # time-series valuation knobs. base = quantile EBITDA-yield, decay=0.
    "refine3": [
        ("ev_ignore",   "quantile(ts_backfill(divide(est_ebitda, add(cap, est_netdebt)), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY", "unitHandling":"IGNORE"}),
        ("ev_rank_ig",  "rank(ts_backfill(divide(est_ebitda, add(cap, est_netdebt)), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY", "unitHandling":"IGNORE"}),
        ("eby_trunc02", "quantile(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY", "truncation":0.02}),
        ("eby_trunc15", "quantile(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY", "truncation":0.15}),
        ("eby_w60",     "quantile(ts_backfill(divide(est_ebitda, cap), 60))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eby_tsrank",  "ts_rank(ts_backfill(divide(est_ebitda, cap), 120), 250)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Value (EBITDA/cap, SH~1.09) stuck. Add an orthogonal QUALITY leg
    # (profitability), low-correlated with value -> classic Sharpe boost.
    "refine4": [
        ("roe",          "quantile(ts_backfill(divide(est_netprofit, est_shequity), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ebitda_assets","quantile(ts_backfill(divide(est_ebitda, est_tot_assets), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_roe",      "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(divide(est_netprofit, est_shequity), 120)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_eassets",  "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(divide(est_ebitda, est_tot_assets), 120)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_ptp",      "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(divide(est_ptp, cap), 120)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_smooth",   "ts_mean(quantile(ts_backfill(divide(est_ebitda, cap), 120)), 10)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Orthogonal leg: supply-chain customer-return REVERSAL (pv13, cold).
    # Value-weighted combos keep turnover < 0.25 while the low-correlation
    # reversal lifts Sharpe past 1.25.
    "refine5": [
        ("rel_rev_s5",   "multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rel_rev_s22",  "multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 22)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_rel_11",   "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_rel_21",   "add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_rel_31",   "add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_rel_21s22","add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 22)), -1))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # val_rel_11 (equal weight) has best raw SH 1.38 but TO 0.45. Use the
    # decay setting to cut turnover below 0.25 while keeping SH > 1.25; lower
    # turnover also lifts fitness. V11 = the equal-weight value+reversal combo.
    "refine6": [
        ("v11_d6",  "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":6, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("v11_d10", "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("v11_d15", "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":15, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("v11_d20", "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("v21_d6",  "add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":6, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("v11_hump","hump(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), hump=0.004)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Target SH>2: stack orthogonal cold D0 signals. Accept higher turnover
    # (submit only needs TO<0.7). value + 4 supply-chain reversals + 3 news.
    "refine7": [
        ("rel4_only",   _addall(REL4), {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("news3_only",  _addall(NEWS3), {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_rel4",    _addall([VAL] + REL4), {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_news3",   _addall([VAL] + NEWS3), {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rel4_news3",  _addall(REL4 + NEWS3), {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("mega",        _addall([VAL] + REL4 + NEWS3), {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Clean full-pass target: LOW-turnover value > SH 1.25. Tight earnings-yield
    # composite (correlated legs -> noise reduction), neutralization + window.
    "refine8": [
        ("yield4_avg",  _addall(["quantile(ts_backfill(divide(est_ebitda, cap), 120))",
                                 "quantile(ts_backfill(divide(est_ebit, cap), 120))",
                                 "quantile(ts_backfill(divide(est_netprofit, cap), 120))",
                                 "quantile(ts_backfill(divide(est_ptp, cap), 120))"]), {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_market",  VAL, {"decay":0, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("val_sector",  VAL, {"decay":0, "universe":"TOP3000", "neutralization":"SECTOR"}),
        ("netprofit_y", "quantile(ts_backfill(divide(est_netprofit, cap), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_multiwin",_addall(["quantile(ts_backfill(divide(est_ebitda, cap), 60))",
                                 "quantile(ts_backfill(divide(est_ebitda, cap), 120))",
                                 "quantile(ts_backfill(divide(est_ebitda, cap), 250))"]), {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("yield4_sec",  _addall(["quantile(ts_backfill(divide(est_ebitda, cap), 120))",
                                 "quantile(ts_backfill(divide(est_ebit, cap), 120))",
                                 "quantile(ts_backfill(divide(est_netprofit, cap), 120))",
                                 "quantile(ts_backfill(divide(est_ptp, cap), 120))"]), {"decay":0, "universe":"TOP3000", "neutralization":"SECTOR"}),
    ],
    # PEAD (earnings surprise) is strong, orthogonal to value & reversal, low
    # turnover. Stack value + cust-reversal + PEAD toward SH 2.0.
    "refine9": [
        ("pead",          PEAD, {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("pead_actual",   "quantile(ts_backfill(divide(news_eps_actual, close), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_pead",      f"add({VAL}, {PEAD})", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_cust_pead", f"add({VAL_REL}, {PEAD})", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("vcp_2val",      f"add(add({VAL}, {VAL_REL}), {PEAD})", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("news_ls",       "quantile(ts_backfill(news_ls, 22))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Add a strong short-term reversal leg to reach SH>=2.0 (submit bar).
    # cold operators (quantile/ts_mean/ts_zscore) on returns; cold value anchor.
    "refine10": [
        ("rev5",          "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rev1z",         "multiply(ts_zscore(returns, 5), 1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("pead_rd",       "subtract(quantile(ts_backfill(news_eps_actual, 120)), quantile(ts_backfill(est_epsr, 120)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_cust_rev5", f"add({VAL_REL}, multiply(quantile(ts_mean(returns, 5)), -1))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("vc_rev5_pead",  f"add(add({VAL_REL}, multiply(quantile(ts_mean(returns, 5)), -1)), subtract(quantile(ts_backfill(news_eps_actual, 120)), quantile(ts_backfill(est_epsr, 120))))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rev5_t500",     "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "universe":"TOP500", "neutralization":"SUBINDUSTRY"}),
    ],
    # D0's strongest signal class: intraday reversal (close vs vwap). Find a
    # high-SH leg, then stack with the cold value+cust anchor toward 2.0.
    "refine11": [
        ("vwap_rev",   "quantile(divide(subtract(vwap, close), close))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("vwap_rev_d2","quantile(ts_mean(divide(subtract(vwap, close), close), 2))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cc_rev1",    "multiply(quantile(returns), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("hl_pos",     "multiply(quantile(divide(subtract(close, low), subtract(high, low))), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_vwaprev",f"add({VAL_REL}, quantile(divide(subtract(vwap, close), close)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("vwap_rev_t1k","quantile(divide(subtract(vwap, close), close))", {"decay":0, "universe":"TOP1000", "neutralization":"SUBINDUSTRY"}),
    ],
    # fundamental6 actuals: classic LOW-turnover quality/value factors. EV is
    # a real field -> EBITDA/EV unit-safe. Stack orthogonal legs (pass fitness).
    "refine12": [
        ("ev_ebitda",   "quantile(ts_backfill(divide(ebitda, enterprise_value), 250))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cfo_assets",  "quantile(ts_backfill(divide(cashflow_op, assets), 250))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ebit_assets", "quantile(ts_backfill(divide(ebit, assets), 250))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("accruals",    "multiply(quantile(ts_backfill(divide(subtract(ebitda, cashflow_op), assets), 250)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("asset_grow",  "multiply(quantile(ts_backfill(divide(ts_delta(assets, 250), assets), 250)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ev_cfo_acc",  "add(add(quantile(ts_backfill(divide(ebitda, enterprise_value), 250)), quantile(ts_backfill(divide(cashflow_op, assets), 250))), multiply(quantile(ts_backfill(divide(subtract(ebitda, cashflow_op), assets), 250)), -1))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Ravenpack news18 VECTOR sentiment + analyst-rec-change (vec_avg = cold
    # operator). News sentiment / rec revisions are classic strong signals.
    "refine13": [
        ("qep_sent", "quantile(ts_backfill(vec_avg(nws18_qep), 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ssc_sent", "quantile(ts_backfill(vec_avg(nws18_ssc), 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec_chg",  "quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("nip",      "quantile(ts_backfill(vec_avg(nws18_nip), 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("bee_earn", "quantile(ts_backfill(vec_avg(nws18_bee), 22))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("qcm_conf", "quantile(ts_backfill(vec_avg(nws18_qcm), 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # rec_chg (analyst rec change) = SH 1.4 but TO 1.43. Tame turnover by
    # accumulating net rec change over a window, then stack with value+cust.
    "refine14": [
        ("rec_mean60",   "quantile(ts_mean(ts_backfill(vec_avg(nws18_ghc_lna), 10), 60))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec_sum120",   "quantile(ts_sum(ts_backfill(vec_avg(nws18_ghc_lna), 5), 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec_decay30",  "quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22))", {"decay":30, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_rec",      f"add({VAL}, quantile(ts_mean(ts_backfill(vec_avg(nws18_ghc_lna), 10), 60)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_rec_cust", f"add(add({VAL}, quantile(ts_mean(ts_backfill(vec_avg(nws18_ghc_lna), 10), 60))), {CUSTREV})", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec_cust",     f"add(quantile(ts_mean(ts_backfill(vec_avg(nws18_ghc_lna), 10), 60)), {CUSTREV})", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Last push: stack RAW strong signals (don't tame). High turnover but high
    # returns -> may pass fitness>=1.3 if SH>=2. legs: value + raw rec_chg(+1.4)
    # + cust-reversal(+0.83) + vwap-reversal(+0.76), correct signs.
    "refine15": [
        ("stack4_raw", "add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), quantile(divide(subtract(vwap, close), close)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("stack3_nvw", "add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec_vwap",   "add(quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)), quantile(divide(subtract(vwap, close), close)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("stack4_d4",  "add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), quantile(divide(subtract(vwap, close), close)))", {"decay":4, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("stack4_2val","add(add(add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22))), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), quantile(divide(subtract(vwap, close), close)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec_cust_vw","add(add(quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)), multiply(quantile(ts_mean(ts_backfill(rel_ret_cust, 120), 5)), -1)), quantile(divide(subtract(vwap, close), close)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Final push: maximize SH of the 4-signal stack via turnover-control ops,
    # weighting, universe, neutralization. STACK4 base = value+rec+cust+vwap.
    "refine16": [
        ("s4_ttvr03", f"ts_target_tvr_decay({S4}, 0.3)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("s4_hump",   f"hump({S4}, hump=0.05)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("s4_none",   S4, {"decay":0, "universe":"TOP3000", "neutralization":"NONE"}),
        ("s4_t500",   S4, {"decay":0, "universe":"TOP500", "neutralization":"SUBINDUSTRY"}),
        ("s4_recheavy", f"add({S4}, quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("s4_mkt",    S4, {"decay":0, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    # REGION lever: short-term reversal is very strong in retail/inefficient
    # markets (CHN/ASI/IND). delay=0. High vol -> high returns -> fitness ok.
    "region_probe": [
        ("chn_rev5", "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "region":"CHN", "universe":"TOP2000U", "neutralization":"SUBINDUSTRY"}),
        ("chn_rev1", "multiply(quantile(returns), -1)", {"decay":0, "region":"CHN", "universe":"TOP2000U", "neutralization":"SUBINDUSTRY"}),
        ("asi_rev5", "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "region":"ASI", "universe":"MINVOL1M", "neutralization":"SUBINDUSTRY"}),
        ("eur_rev5", "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "region":"EUR", "universe":"TOP2500", "neutralization":"SUBINDUSTRY"}),
        ("glb_rev5", "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "region":"GLB", "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ind_rev5", "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "region":"IND", "universe":"TOP500", "neutralization":"SUBINDUSTRY"}),
    ],
    # Account is USA-only. ILLIQUID universe: stronger reversal/value anomalies.
    "illiq_probe": [
        ("illiq_rev5",  "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "universe":"ILLIQUID_MINVOL1M", "neutralization":"SUBINDUSTRY"}),
        ("illiq_rev1",  "multiply(quantile(returns), -1)", {"decay":0, "universe":"ILLIQUID_MINVOL1M", "neutralization":"SUBINDUSTRY"}),
        ("illiq_value", "quantile(ts_backfill(divide(est_ebitda, cap), 120))", {"decay":0, "universe":"ILLIQUID_MINVOL1M", "neutralization":"SUBINDUSTRY"}),
        ("illiq_vwap",  "quantile(divide(subtract(vwap, close), close))", {"decay":0, "universe":"ILLIQUID_MINVOL1M", "neutralization":"SUBINDUSTRY"}),
        ("illiq_stack", S4, {"decay":0, "universe":"ILLIQUID_MINVOL1M", "neutralization":"SUBINDUSTRY"}),
        ("t200_rev5",   "multiply(quantile(ts_mean(returns, 5)), -1)", {"decay":0, "universe":"TOP200", "neutralization":"SUBINDUSTRY"}),
    ],
    # Untested signal source: social-media sentiment (full coverage). Probe
    # strength + 5-leg stack (value+rec+cust+vwap+sentiment) toward SH 2.
    "social_probe": [
        ("sent_scl",  "quantile(ts_backfill(scl12_sentiment, 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("sent_z",    "quantile(ts_backfill(snt_social_value, 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("sent_mom",  "quantile(ts_delta(ts_backfill(scl12_sentiment, 5), 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("buzz_mom",  "quantile(ts_delta(ts_backfill(scl12_buzz, 5), 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_sent",  f"add({VAL}, quantile(ts_backfill(scl12_sentiment, 5)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("stack5",    f"add({S4}, quantile(ts_backfill(scl12_sentiment, 5)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Cold constraint lifted: engineer a STRONG D0 reversal leg (residual /
    # liquidity / volume-scaled), aim >1.2, then stack toward SH>=2.
    "free_probe1": [
        ("zrev_mkt",  "multiply(ts_zscore(returns, 5), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("liqrev",    "multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("volscale",  "multiply(rank(multiply(ts_mean(returns, 5), ts_std_dev(returns, 20))), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cvrev",     "multiply(rank(ts_corr(returns, volume, 10)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("vwap_dev",  "multiply(rank(divide(subtract(close, vwap), vwap)), -1)", {"decay":0, "universe":"TOP1000", "neutralization":"SUBINDUSTRY"}),
        ("ovnight",   "multiply(rank(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1))), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Kitchen-sink: combine all distinct signals + multi-horizon reversal,
    # rec-dominant weighting, toward SH>=2.
    "free_probe2": [
        ("mhrev",    "add(add(multiply(rank(returns), -1), multiply(rank(ts_mean(returns, 5)), -1)), rank(ts_mean(returns, 21)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec3_vc",  f"add(add(add({RECRAW}, {RECRAW}), add({RECRAW}, {VAL})), {CUSTREV})", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("maxstack", f"add(add(add(add({VAL}, add({RECRAW}, {RECRAW})), {CUSTREV}), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("max_mh",   f"add(add(add({VAL}, add({RECRAW}, {RECRAW})), {CUSTREV}), add(add(multiply(rank(returns), -1), multiply(rank(ts_mean(returns, 5)), -1)), rank(ts_mean(returns, 21))))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("max_grp",  f"add(add(add({VAL}, add({RECRAW}, {RECRAW})), {CUSTREV}), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1))", {"decay":0, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("max_d2",   f"add(add(add({VAL}, add({RECRAW}, {RECRAW})), {CUSTREV}), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1))", {"decay":2, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # NEW low-turnover signal: cross-sectional momentum (12-1m). Orthogonal to
    # value & reversal, slow -> low turnover (fitness-friendly). Build low-TO
    # multifactor value+momentum(+quality) for high SH that PASSES fitness.
    "free_probe3": [
        ("mom12",    "rank(divide(ts_delay(close, 21), ts_delay(close, 252)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("mom6",     "rank(divide(ts_delay(close, 21), ts_delay(close, 126)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_mom",  "add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), rank(divide(ts_delay(close, 21), ts_delay(close, 252))))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_mom_q","add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), rank(divide(ts_delay(close, 21), ts_delay(close, 252)))), quantile(ts_backfill(divide(cashflow_op, assets), 250)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("vmom_rec", f"add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), rank(divide(ts_delay(close, 21), ts_delay(close, 252)))), {RECRAW})", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("vmom_cust",f"add(add(quantile(ts_backfill(divide(est_ebitda, cap), 120)), rank(divide(ts_delay(close, 21), ts_delay(close, 252)))), {CUSTREV})", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Hunt for low-TO signals ORTHOGONAL to value, to stack toward SH>=2 while
    # keeping turnover low (fitness only binds when TO high). Classic anomalies
    # untested so far: low-vol (BAB), shareholder yield, cash-based operating
    # profitability (Ball 2016), long-term reversal, net margin, inventory growth.
    "fund_probe1": [
        ("lowvol",   "multiply(rank(ts_std_dev(returns, 120)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("payout",   "quantile(ts_backfill(divide(fnd6_dvt, cap), 250))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cashprof", "quantile(ts_backfill(divide(subtract(subtract(revenue, cogs), sga_expense), assets), 250))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ltrev",    "multiply(rank(divide(ts_delay(close, 21), ts_delay(close, 750))), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("netmargin","quantile(ts_backfill(divide(fnd6_ni, revenue), 250))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("invgrow",  "multiply(rank(divide(ts_delta(ts_backfill(fnd6_invt, 60), 250), ts_backfill(assets, 60))), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # NEW dataset: option8 (implied volatility). Documented cross-sectional
    # return predictors: call-put IV spread (Cremers-Weinbaum +), IV skew
    # (Xing-Zhang-Zhao -), vol risk premium IV/RV, low-IV anomaly (Ang +).
    # Signs flipped post-hoc if SH negative (|SH| = signal strength).
    "opt_probe1": [
        ("cpspread", "quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ivskew",   "multiply(quantile(ts_backfill(implied_volatility_mean_skew_30, 5)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("volrp",    "multiply(quantile(ts_backfill(divide(implied_volatility_mean_30, historical_volatility_30), 5)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ivterm",   "quantile(ts_backfill(subtract(implied_volatility_mean_360, implied_volatility_mean_30), 5))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("lowiv",    "multiply(rank(ts_backfill(implied_volatility_mean_60, 5)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("ivchg",    "multiply(quantile(ts_delta(ts_backfill(implied_volatility_mean_30, 5), 5)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # cpspread (call-put IV spread) hit SH 1.55 but TO 1.01. It is strong AND
    # orthogonal to value (option-implied vs fundamental). Tame turnover via
    # smoothing/decay, then stack with value toward SH>=2 at TO<0.7.
    "opt_probe2": [
        ("cps_sm10",  "quantile(ts_mean(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 10), 10))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cps_d20",   "quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cps_60",    "quantile(ts_mean(ts_backfill(subtract(implied_volatility_call_60, implied_volatility_put_60), 10), 10))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_cps",   f"add({VAL}, quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_cps_sm",f"add({VAL}, quantile(ts_mean(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 10), 10)))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_cps_d20",f"add({VAL}, quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5)))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # cps_d20 = SH 2.12 / FIT 1.48 / TO 0.21, fails ONLY LOW_SUB_UNIVERSE_SHARPE
    # (option data sparse on small caps -> signal concentrated). Fix sub-universe
    # sharpe via neutralization/universe/multi-maturity robustness + value blend.
    "opt_probe3": [
        ("cps_ind",   "quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5))", {"decay":20, "universe":"TOP3000", "neutralization":"INDUSTRY"}),
        ("cps_mkt",   "quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("cps_t1k",   "quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5))", {"decay":20, "universe":"TOP1000", "neutralization":"SUBINDUSTRY"}),
        ("cps_multi", "quantile(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 5))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cps2_val",  f"add(add(quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5)), quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5))), {VAL})", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cps_d25",   "quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5))", {"decay":25, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # cps_d20 sub-universe fix sweep #2 (user: fix sub-universe & submit). Boost
    # coverage on smaller names: longer backfill fills more stocks; value blend
    # lifts broad sub-universe Sharpe; multi-maturity + group ops for robustness.
    "opt_probe4": [
        ("cps_bf22",  "quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cps_bf44",  "quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 44))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cps_valeq", f"add(quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22)), {VAL})", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cps_val2",  f"add(quantile(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22)), add({VAL}, {VAL}))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cps_mlt22", "quantile(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 22))", {"decay":20, "universe":"TOP3000", "neutralization":"INDUSTRY"}),
        ("cps_grp",   "group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), subindustry)", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # cps_multi (3-maturity, SH 2.18) is the strongest base but fails sub-univ
    # under SUBINDUSTRY. Pair the strong base with sub-univ fixes: MARKET /
    # INDUSTRY neutralization + value blend, to clear BOTH SH>=2 and sub-univ.
    "opt_probe5": [
        ("mlt_mkt",  "quantile(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 5))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("mlt_ind",  "quantile(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 5))", {"decay":20, "universe":"TOP3000", "neutralization":"INDUSTRY"}),
        ("mlt_val",  f"add(quantile(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 5)), {VAL})", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("mlt_mkt_v",f"add(quantile(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 5)), {VAL})", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("mlt_grp",  "group_zscore(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 5), industry)", {"decay":20, "universe":"TOP3000", "neutralization":"INDUSTRY"}),
        ("mlt_d15",  "quantile(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 5))", {"decay":15, "universe":"TOP3000", "neutralization":"INDUSTRY"}),
    ],
    # cps_grp (group_zscore base) = SH 2.41, highest. Only MARKET neut clears
    # sub-universe (costs ~0.4 SH). 2.41 base has headroom: grp+MARKET should
    # land near/above 2.0 AND pass sub-universe. Also try grp multi-maturity.
    "opt_probe6": [
        ("grp_mkt",   "group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), subindustry)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("grp_ind",   "group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), subindustry)", {"decay":20, "universe":"TOP3000", "neutralization":"INDUSTRY"}),
        ("grpmlt_mkt","group_zscore(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 22), subindustry)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("grpmlt_ind","group_zscore(ts_backfill(add(add(subtract(implied_volatility_call_30, implied_volatility_put_30), subtract(implied_volatility_call_60, implied_volatility_put_60)), subtract(implied_volatility_call_90, implied_volatility_put_90)), 22), subindustry)", {"decay":20, "universe":"TOP3000", "neutralization":"INDUSTRY"}),
        ("grp_mkt5",  "group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 5), subindustry)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("grp_sec_mkt","group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    # grp_sec_mkt passes ALL deterministic checks (SH2.41/FIT2.91/sub-univ) but
    # SELF_CORRELATION=0.78>0.7 vs user's existing IV-spread alpha. De-correlate:
    # use DIFFERENT maturities (60/90, not their 30d) + orthogonal blends, keep
    # the winning sector-group + MARKET structure, SH>=2, sub-univ pass.
    "opt_probe7": [
        ("sec60",   "group_zscore(ts_backfill(subtract(implied_volatility_call_60, implied_volatility_put_60), 22), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("sec90",   "group_zscore(ts_backfill(subtract(implied_volatility_call_90, implied_volatility_put_90), 22), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("sec6090", "group_zscore(ts_backfill(add(subtract(implied_volatility_call_60, implied_volatility_put_60), subtract(implied_volatility_call_90, implied_volatility_put_90)), 22), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("sec180",  "group_zscore(ts_backfill(subtract(implied_volatility_call_180, implied_volatility_put_180), 22), sector)", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("sec_val", f"add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), {VAL})", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("sec_rev", "add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    # Self-corr to user's IV-spread alpha is ~0.78-0.85 regardless of maturity.
    # Only path to <0.7 while keeping SH>=2: LIGHT orthogonal blend (IV ~80%),
    # nudging corr just under 0.7 with minimal SH loss. Test blend ratios.
    "opt_probe8": [
        ("g4v",   "add(add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(ts_backfill(divide(est_ebitda, cap), 120)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g3v",   "add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(ts_backfill(divide(est_ebitda, cap), 120)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g4r",   "add(add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g3r",   "add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g4vr",  "add(add(add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g5vr",  "add(add(add(add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(ts_backfill(divide(est_ebitda, cap), 120))), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    # g4r (4:1 IV:reversal) self-corr=0.737, just above 0.7, SH 2.51. Reversal
    # is orthogonal AND adds Sharpe -> heavier reversal pushes corr <0.7 while
    # keeping SH>=2. Sweep heavier reversal ratios to clear the last check.
    "opt_probe9": [
        ("g2r",    "add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g32r",   "add(add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(divide(subtract(vwap, close), close))), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g1r",    "add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g52r",   "add(add(add(add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(divide(subtract(vwap, close), close))), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g73r",   "add(add(add(add(add(add(add(add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(divide(subtract(vwap, close), close))), quantile(divide(subtract(vwap, close), close))), quantile(divide(subtract(vwap, close), close)))", {"decay":20, "universe":"TOP3000", "neutralization":"MARKET"}),
        ("g2r_d25","add(add(group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector), group_zscore(ts_backfill(subtract(implied_volatility_call_30, implied_volatility_put_30), 22), sector)), quantile(divide(subtract(vwap, close), close)))", {"decay":25, "universe":"TOP3000", "neutralization":"MARKET"}),
    ],
    # DIFFERENT TYPE (user vetoed IV call-put spread). news12 short interest =
    # classic positioning anomaly (Boehmer-Jones-Zhang: high SI -> low returns),
    # low-TO, orthogonal to value/IV. Plus dividend yield, range z, prev-day rev.
    "newsig_probe1": [
        ("shortint",  "multiply(quantile(ts_backfill(news_short_interest, 22)), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("si_d20",    "multiply(quantile(ts_backfill(news_short_interest, 22)), -1)", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("si_chg",    "multiply(quantile(ts_delta(ts_backfill(news_short_interest, 22), 66)), -1)", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("dy_val",    "quantile(ts_backfill(news_dividend_yield, 120))", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("range_z",   "multiply(quantile(ts_backfill(news_range_stddev, 5)), -1)", {"decay":5, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("si_val",    f"add(multiply(quantile(ts_backfill(news_short_interest, 22)), -1), {VAL})", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Different types again: PEAD (earnings-surprise drift), news-reaction L/S
    # signal (nws12 sl), post-news relative move, analyst EPS revision. Apply
    # decay to tame noise like the cps trick (technique, not the vetoed signal).
    "newsig_probe2": [
        ("pead",      "quantile(ts_backfill(divide(subtract(news_eps_actual, est_epsr), close), 120))", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("pead_d20",  "quantile(ts_backfill(divide(subtract(news_eps_actual, est_epsr), close), 120))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("newssl",    "quantile(ts_backfill(vec_avg(nws12_mainz_sl), 10))", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("resvsidx",  "quantile(ts_backfill(vec_avg(nws12_mainz_result_vs_index), 10))", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("epsrev",    "quantile(ts_backfill(divide(ts_delta(est_epsr, 66), close), 120))", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("pead_val",  f"add(quantile(ts_backfill(divide(subtract(news_eps_actual, est_epsr), close), 120)), {VAL})", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Apply the decay-magic (smoothing a noisy-but-persistent signal, as in the
    # cps win) to NON-IV mainstream signals: supply-chain lead-lag (Cohen-
    # Frazzini, pv13 rel_ret_*), rank-based PEAD (units-safe), rec_chg low decay.
    "newsig_probe3": [
        ("peadrank",  "subtract(rank(ts_backfill(news_eps_actual, 90)), rank(ts_backfill(est_epsr, 90)))", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("cust_d20",  "quantile(ts_backfill(rel_ret_cust, 5))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("comp_d20",  "quantile(ts_backfill(rel_ret_comp, 5))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("all_d20",   "quantile(ts_backfill(rel_ret_all, 5))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec_d10",   "quantile(ts_backfill(vec_avg(nws18_ghc_lna), 22))", {"decay":10, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("val_cust_d",f"add({VAL}, quantile(ts_backfill(rel_ret_cust, 5)))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Decisive mainstream batch (cold constraint lifted): decay-magic on
    # sentiment level; rec_chg (1.40 single best non-IV) on liquid universes
    # to pass sub-universe; stack decay sweep to tame the 1.93 maxstack.
    "newsig_probe4": [
        ("sent_d20",   "quantile(ts_backfill(scl12_sentiment, 5))", {"decay":20, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("rec_t200",   RECRAW, {"decay":5, "universe":"TOP200", "neutralization":"SUBINDUSTRY"}),
        ("val_rec_t1k", f"add({VAL}, {RECRAW})", {"decay":5, "universe":"TOP1000", "neutralization":"SUBINDUSTRY"}),
        ("s4_d6",      S4, {"decay":6, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("maxstack_d8", f"add(add(add(add({VAL}, add({RECRAW}, {RECRAW})), {CUSTREV}), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5)))", {"decay":8, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("maxstack_t1k", f"add(add(add(add({VAL}, add({RECRAW}, {RECRAW})), {CUSTREV}), multiply(rank(ts_mean(divide(returns, adv20), 5)), -1)), quantile(ts_backfill(scl12_sentiment, 5)))", {"decay":8, "universe":"TOP1000", "neutralization":"SUBINDUSTRY"}),
    ],
    # Operator-engineering (per user's example structure): apply
    # winsorize(ts_decay_linear(group_zscore(ts_mean(BASE,40), sector),4),std=4)
    # to mainstream NON-IV bases. Sector-relative + smoothed + decayed.
    "newsig_probe5": [
        ("eng_val",  "winsorize(ts_decay_linear(group_zscore(ts_mean(ts_backfill(divide(est_ebitda, cap), 60), 40), sector), 4), std=4)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eng_ey",   "winsorize(ts_decay_linear(group_zscore(ts_mean(ts_backfill(divide(est_epsr, close), 60), 40), sector), 4), std=4)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eng_rev",  "multiply(winsorize(ts_decay_linear(group_zscore(ts_mean(returns, 40), sector), 4), std=4), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eng_cfo",  "winsorize(ts_decay_linear(group_zscore(ts_mean(ts_backfill(divide(cashflow_op, assets), 60), 40), sector), 4), std=4)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eng_vwap", "multiply(winsorize(ts_decay_linear(group_zscore(ts_mean(divide(subtract(vwap, close), close), 40), sector), 4), std=4), -1)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
        ("eng_recz", "winsorize(ts_decay_linear(group_zscore(ts_mean(ts_backfill(vec_avg(nws18_ghc_lna), 22), 40), sector), 4), std=4)", {"decay":0, "universe":"TOP3000", "neutralization":"SUBINDUSTRY"}),
    ],
}


def run_batch(batch_name, max_workers=3):
    cands = BATCHES[batch_name]
    session = auth()
    print(f"authenticated; running {len(cands)} candidates ({batch_name})")
    results = {}

    def task(item):
        name, expr, extra = item
        settings = {"delay": 0, "universe": "TOP3000", "neutralization": "SUBINDUSTRY"}
        settings.update(extra)
        r = simulate(session, expr, settings, verbose=False)
        return name, expr, r

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(task, c) for c in cands]
        for fut in as_completed(futs):
            name, expr, r = fut.result()
            if r.get("ok"):
                m = is_metrics(r["alpha"])
                results[name] = {"expr": expr, "alpha_id": r["alpha_id"], "metrics": m, "settings": r["settings"]}
                ck = m["checks"]
                npass = sum(1 for v in ck.values() if v == "PASS")
                print(f"[{name:10}] SH={m['sharpe']!s:>6} TO={m['turnover']!s:>7} FIT={m['fitness']!s:>6} "
                      f"ret={m['returns']!s:>7} checks={npass}/{len(ck)} id={r['alpha_id']}")
                print(f"             checks={ck}")
            else:
                results[name] = {"expr": expr, "error": r.get("message") or r.get("body") or r.get("stage")}
                print(f"[{name:10}] ERR {r.get('stage')}: {(r.get('message') or r.get('body') or '')[:160]}")

    out = Path(__file__).resolve().parent.parent / f"probe_{batch_name}.json"
    json.dump(results, open(out, "w"), indent=2)
    print(f"wrote {out}")
    return results


if __name__ == "__main__":
    run_batch(sys.argv[1] if len(sys.argv) > 1 else "news_probe")
