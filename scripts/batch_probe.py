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

BATCHES = {
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
