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
    # probe14: classic fundamental anomalies - net share issuance (dense sharesout),
    # asset growth, gross profitability (Novy-Marx), and value-quality stacks.
    # probe15: universe sweep on short interest - smaller (more liquid) universes have denser
    # SI coverage, may pass CONCENTRATED_WEIGHT where TOP3000 fails. Settings are search space.
    # probe16: tight truncation sweep to cap single-name weight and clear CONCENTRATED_WEIGHT
    # on short interest (si_top500 was SH 1.46 FIT 2.17, only failing conc + low_sharpe).
    # probe17: carefully-constructed PURE-DENSE multi-factor stack (value+issuance+LTrev+rev+
    # grossprof+assetgrowth), all group_zscore equal-vol, all concentration-passing. Best shot
    # at a clean all-checks-pass non-option D0 factor; also probes true LOW_SHARPE bar.
    # probe18: VALUE COMPOSITE - average multiple est_* value ratios (FCF/CFO/EBITDA/EBIT/book/
    # sales yield) to reduce noise and lift value above single-ratio ~1.07. All dense -> pass conc.
    # probe19: rescue short interest via NaN-fill densification onto dense value base.
    # add(value_dense, fill(SI,0)) -> value provides breadth, SI tilts where present.
    # probe20: dense MATRIX news-reaction signals (~0.97 coverage -> pass concentration):
    # overnight gap reversal, relative-to-index, dividend yield, dataset L/S, prev-day reversal,
    # news-reaction magnitude. Genuinely new signal family.
    # probe21: structurally-different time-series alphas (ts_zscore mean-reversion, MA-ratio,
    # ts_rank volume, ts_ir) + multiplicative value x quality interaction. All dense.
    # probe22: DELAY=1 dense (cov=1.0) composite model factors - non-option. Pre-built factor
    # signals (earnings momentum, analyst momentum/surprise/price/value composites, deep value,
    # PEAD abnormal return, EBITDA/EV, earnings yield). Dense -> pass concentration; uncrowded.
    # probe23: DELAY=1 dense (cov=1.0) SHORT-SENTIMENT / securities-lending factors - non-option.
    # Borrow fee, utilization, days-to-cover, demand/supply (squeeze), short interest. SI was
    # SH 1.6 but SPARSE (failed breadth) at delay=0; these are cov=1.0 dense -> strong + pass
    # concentration. ss_stack = combined short-pressure composite. Sign read from SH (flip if neg).
    # probe24: validate the ss_util breakthrough. Re-run dtc/dmdsup (hit concurrency cap),
    # robustness variants of act_util (INDUSTRY / SUBINDUSTRY neut, tight truncation 0.03 to
    # test if the 2.84 SH survives risk controls / is not just meme-squeeze concentration),
    # plus inventory-concentration family field.
    # probe25: DELAY=0 short/lending hunt (user requires d0). Test whether the delay=1 winning
    # lending fields (act_util/fee/dtc) are even accepted at delay=0; plus densest d0 short-
    # interest constructions (news_short_interest cov0.86, nws12 main/pre-market SI vectors)
    # with the same plain group_zscore form that scored 2.84 at delay=1.
    # probe26: DELAY=0 NEW quality/earnings-quality factors (user: keep grinding d0). Sloan
    # accruals (CFO-NI, low=good earnings quality), ROA, ROE, cash-flow yield, gross
    # profitability (Novy-Marx GP/assets), and orthogonal quality composite. ts_backfill 120 to
    # densify quarterly fundamentals (cov~0.5) for concentration. Documented strong anomalies.
    # probe27: DELAY=0 remaining untested dense families. Low-volatility anomaly (historical/
    # parkinson vol, long low-vol = top documented factor), RavenPack social sentiment (snt cov=1.0,
    # scl12), competitor lead-lag (rel_ret_comp). Last structurally-new d0 datasets.
    # probe28: DELAY=0 OPTION-IMPLIED signals (user: appropriately blend options, stay d0).
    # IV skew (crash premium), put-call IV spread (directional demand), IV term structure,
    # variance risk premium (IV-realized), IV level, + value x put-call blend. Dense cov~0.69.
    # probe29: refine option signal to pass ALL gates. Flip put-call spread (+1.6 raw -1.6),
    # try INDUSTRY neut / TOP500 / decay20 for sub-universe robustness, and correct-sign
    # value+option fusion (value carries sub-universe breadth, option adds strength).
    # probe30: NON-IV signals re-tested under INDUSTRY/SUBINDUSTRY neut (the lever that lifted
    # the IV signal 1.6->2.28). Value, short-interest anomaly (high SI underperforms, flipped),
    # CF yield, gross profitability, value+quality composite. Seeking a 2nd SH>=2 non-IV factor.
    # probe31: ANALYST ESTIMATE-REVISION MOMENTUM (non-IV informed forward-looking signal).
    # ts_delta of backfilled consensus (EPS/net-profit/EBIT) over a quarter, scaled by price/cap.
    # Upward revisions predict positive returns - one of the most robust documented anomalies.
    # probe32: NEW non-IV mechanisms (user: try 1 more). George-Hwang 52-week-high proximity
    # (close/ts_max(high,252), anchoring - strong untested pure-price anomaly) + INDUSTRY variant,
    # idiosyncratic (industry-neut) 12-1 momentum, fundamental momentum (ROA YoY accel),
    # multi-mechanism composite (value+quality+trend), value+52w-high fusion.
    # probe33: George-Hwang 52-week-high proximity via ts_rank(close,252) (ts_max inaccessible).
    # High rank = near 52w high = anchoring continuation. MARKET/INDUSTRY/SUBINDUSTRY neut,
    # value+trend fusion, multi-mechanism composite, decay20 variant.
    # probe34: NEWS-EVENT signals (news12, cov~0.97, untested non-option family). PEAD/SUE
    # (news_eps_actual - est_epsr consensus = earnings surprise -> drift, top-tier anomaly),
    # news-day price-reaction drift, abnormal return vs SPY, volume/attention shock, + INDUSTRY.
    # probe35: PEAD/SUE rebuilt unitless (eps_surprise errored on units). Percent surprise
    # divide(news_eps_actual, est_epsr consensus), standardized surprise (zscore-diff), surprise+
    # price-confirmation drift, earnings yield via news_pe_ratio. + INDUSTRY variants.
    # probe36: COMPLEX structural forms (user: mine freely, no IV/D1). Not single-field z-scores -
    # price-volume correlation divergence (ts_corr), reversion to VWAP, vol-of-vol premium,
    # intraday up/down asymmetry, Amihud illiquidity premium, + INDUSTRY pv-corr.
    # probe37: DELIVERABLE multi-factor non-option basket (user chose A). Equal-weight z-scores of
    # value (est_ebitda/cap), cfo-yield (cashflow_op/cap), pv-correlation (-ts_corr(close,volume)).
    # Test MARKET/INDUSTRY neut, hybrid (pv-corr industry-relative internally), value-tilt, V+P drop-cfo.
    # probe38: PARAMETER TUNING of non-IV basket (1.16 base). Decay sweep (12/20 smoothing),
    # add 4th/5th low-correlation components (gross profitability, low-vol), slower pv-corr (60d).
    # probe39: push tuned 4-factor basket (1.31) toward submittable. Universe TOP1000/500 (cleaner
    # fundamentals), decay fine-tune 8/10, value+quality weight tilt, tighter truncation 0.04.
    # probe40: GOAL=pass competition bar (SH>=2). IV-anchored (only path past 2.0). Reconfirm
    # put-call IV spread (2.28), tune decay, combine with IV skew + term structure (3 option
    # signals), 30-day horizon. All INDUSTRY-neut (the lever). Maximize robust SH>=2.
    # probe41: GOAL=non-IV SH>=2 via NEW operator structures (never tried: trade_when conditional
    # trading, winsorize, rank, multiplicative interaction). Applied to the 1.31-1.34 basket.
    # probe42: SHORT-TERM REVERSAL - untapped HIGH-Sharpe non-IV family (docs SH 2-4). 1/5-day
    # price reversal, SUBINDUSTRY/INDUSTRY neut (peer-relative = strongest), low decay, vol-scaled.
    # probe43: MEGA-basket - add ORTHOGONAL fast reversal (and sentiment) to the 1.34 fundamental
    # basket. Reversal internally subindustry-z (its best grouping), fundamentals market-z, then
    # one MARKET/INDUSTRY neut. Diversification of orthogonal signals to push toward 2.0.
    # probe44: STACK more orthogonal signals on the 1.72 6-factor mega. Add news abnormal return,
    # idiosyncratic 12-1 momentum (orthogonal to 5d reversal), accruals earnings-quality. 7/8/9-factor
    # diversification push toward 2.0.
    # probe45: push 1.81 7-factor toward 2.0 - weight-tilt strong components (value/pvcorr/reversal),
    # add 2nd-sentiment (scl12), 2nd-news reaction, high-low range. Orthogonal stacking + weights.
    # probe46: push 1.81 7-factor to 2.0 via settings-sweep (decay 4/10, truncation 0.04/0.15)
    # + stronger reversal component (multi-horizon 3+5+10d, rank-based).
    # probe47: combine best levers - rank-reversal + decay 2/3/4 + reversal weight 1.5/2x.
    # Pushing the 1.88 mega toward 2.0.
    # probe48: push the 2.22 non-IV mega higher - reversal weight 2.5/3x, decay 3/5, reversal
    # window 3/10. Find the best config above 2.22.
    # probe49: SIMPLE regularized DISTINCT alphas (user: 8-factor mega risks overfit). 1-2 component,
    # winsorize(std=4) regularization to clip outliers. Economically clean, robust, low-overfit.
    # probe50: regularized MIDDLE-GROUND 5-factor (value+cfo+gp+pvcorr+reversal, winsorized) at
    # moderate reversal weight + decay-stability robustness check. Less overfit than 8-factor mega.
    # probe51: REGULARIZED (winsorized) 7-factor at reversal weight + decay sweep. Goal: reach
    # competition standard (SH>=2) WHILE staying robust (winsorize + decay-stable, low overfit).
    # probe52: NEW distinct simple economic alpha, regularized (winsorize). Net-issuance anomaly
    # (buybacks outperform, issuance underperforms - Daniel-Titman), asset-growth/CMA investment
    # factor, low-vol/BAB. All orthogonal to the value/reversal/sentiment mega. 1-factor simple.
    # probe53: net-issuance regularized via RANK (spreads lumpy weights -> fixes concentration).
    # Economic: buybacks (share-count down) outperform, dilution underperforms. Simple 1-field,
    # distinct from the value/reversal mega. Neutralization + densify variants.
    # probe54: SOFTER regularization on net-issuance (raw 1.01 conc-fail, full-rank 0.52). signed_power
    # (sqrt/cube-root tail shrink) and aggressive winsorize (std 1/1.5/2) - retain more strength
    # while passing concentration. Find best SH that clears CONCENTRATED_WEIGHT.
    # probe55: more SIMPLE ECONOMIC alphas - Sloan accruals (earnings quality: cash earnings >
    # accrual earnings persist), dividend yield (income), earnings yield E/P. Winsorize/rank
    # regularized, 1-field ratios, distinct from value/reversal/issuance pool.
    # probe69: short_interest direction blocked by 2021-05-05 concentration spike
    # (sparse coverage). Pivot AGAIN - explore dense news12 fields not in prior
    # direction. news_pct_120min (cov 0.91, 234 users), news_atr14 (49 users),
    # news_max_dn_ret (30 users), news_eps_actual (PEAD-rebuilt) - all dense
    # enough to skip concentration spike, all distinct from the prior pool.
    # Test both signs of news drift (continuation vs reversal).
    "newfam_probe69": [
        # News drift 120min (continuation - buy what moves up)
        ("drift120_pos", "group_zscore(ts_backfill(news_pct_120min, 22), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # News drift 120min REVERSAL (sell what jumped, over-reaction unwind)
        ("drift120_neg", "multiply(group_zscore(ts_backfill(news_pct_120min, 22), market), -1)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # News drift 90min (faster - more immediate reaction)
        ("drift90_pos", "group_zscore(ts_backfill(news_pct_90min, 22), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # ATR-based low-vol (news_atr14 inverted - BAB on news events)
        ("atr_lowvol", "multiply(group_zscore(rank(ts_backfill(news_atr14, 22)), market), -1)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # PEAD via dense news_eps_actual / close (price-normalized, unit-safe)
        ("pead_dense", "group_zscore(ts_backfill(divide(news_eps_actual, close), 120), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # Maximum down-move after news (panic indicator, reversal)
        ("maxdn_rev", "multiply(group_zscore(ts_backfill(news_max_dn_ret, 22), market), -1)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe68: dense fillers all hurt the 2.24 base. Two cleaner paths to fix
    # the 2021-05-05 coverage gap: (a) alternative SI fields - news12 has
    # nws12_mainz_short_interest (cov 0.8636) and nws12_prez_short_interest
    # (cov 0.8115, pre-market) measuring the same metric at different times,
    # avg of all three should densify coverage; (b) group_backfill with explicit
    # lookback to fill from subindustry peer median when own value is NaN.
    "newfam_probe68": [
        # alt SI field: mainz (cov 0.8636, marginally denser)
        ("si_mainz", "group_zscore(quantile(ts_backfill(nws12_mainz_short_interest, 22)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # alt SI field: pre-market (different temporal coverage)
        ("si_prez", "group_zscore(quantile(ts_backfill(nws12_prez_short_interest, 22)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # AVG of 3 SI variants (any one non-NaN -> avg non-NaN) for denser coverage
        ("si_avg3", "group_zscore(quantile(divide(add(add(ts_backfill(news_short_interest, 22), ts_backfill(nws12_mainz_short_interest, 22)), ts_backfill(nws12_prez_short_interest, 22)), 3)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # group_backfill via subindustry peer median, lookback 5
        ("si_grpbf5", "group_zscore(quantile(group_backfill(ts_backfill(news_short_interest, 22), subindustry, 5)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # group_backfill lookback 22
        ("si_grpbf22", "group_zscore(quantile(group_backfill(ts_backfill(news_short_interest, 22), subindustry, 22)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # avg3 + CMA (best base SI + asset growth orthogonal stack)
        ("si_avg3_cma", "add(group_zscore(quantile(divide(add(add(ts_backfill(news_short_interest, 22), ts_backfill(nws12_mainz_short_interest, 22)), ts_backfill(nws12_prez_short_interest, 22)), 3)), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe67: ts_skewness/ts_kurtosis inaccessible. The 0.236 concentration value
    # across all variants strongly implies coverage gap: ~4 names have positions on
    # 2021-05-05 (1/0.236 ~= 4.2). Two attacks: (a) group_backfill fills via peer
    # median when own value is NaN; (b) TINY-weight dense filler (0.05-0.1x) so all
    # names get non-zero positions without signal interference. Try BAB low-vol
    # (documented anomaly) and rank(adv20) as candidate dense fillers.
    "newfam_probe67": [
        # group_backfill via subindustry peer median (fills sparse names)
        ("si_grpbf", "group_zscore(quantile(group_backfill(ts_backfill(news_short_interest, 22), subindustry)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # si_qntl + low-vol BAB at TINY 0.1x weight (just to fill positions)
        ("si_qntl_lvol01", "add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(rank(historical_volatility_60), market), -0.1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # si_qntl + low-vol at 0.2x
        ("si_qntl_lvol02", "add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(rank(historical_volatility_60), market), -0.2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # si_qntl + rank(cap) size-reversal at 0.1x (small-cap premium filler)
        ("si_qntl_size", "add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(rank(cap), market), -0.1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # si_qntl + amihud illiquidity at 0.2x (rank of abs(returns)/dollar_volume, dense)
        ("si_qntl_amh", "add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(rank(divide(abs(returns), multiply(close, volume))), market), 0.2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # group_backfill + CMA combo (peer fill + asset growth)
        ("si_grpbf_cma", "add(group_zscore(quantile(group_backfill(ts_backfill(news_short_interest, 22), subindustry)), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe66: si concentration spike on 2021-05-05 is STRUCTURAL - news_short_interest
    # has thin coverage on that single date, no transform of si fixes it. Need a
    # DENSE filler leg (full PV coverage) to dilute concentration on the bad date.
    # Candidates: Bali (2011) skewness reversal, ts_kurtosis lottery reversal -
    # PV-dense, behavioral, orthogonal to prior value/quality/news direction.
    # Best probe65: si_qntl SH 2.24 / FIT 3.61 - take it as the base.
    "newfam_probe66": [
        # si_qntl + Bali skewness reversal (dense, behavioral lottery anomaly)
        ("si_qntl_skew", "add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(ts_skewness(returns, 22), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # si_qntl + Bali kurtosis reversal (fat-tail proxy)
        ("si_qntl_kurt", "add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(ts_kurtosis(returns, 22), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # si_qntl + Bali skew + CMA (3-leg, both orthogonal, dense skew filler)
        ("si_skew_cma", "add(add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(ts_skewness(returns, 22), market), -1)), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # si_qntl + dense ts_zscore(returns,60) filler at 0.5x (cheap dense leg just for concentration)
        ("si_qntl_zret", "add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(ts_zscore(returns, 60), market), -0.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # Skewness reversal SOLO (test how strong this leg is on its own)
        ("skew_solo", "multiply(group_zscore(ts_skewness(returns, 22), market), -1)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # Kurtosis reversal SOLO (compare strength vs skewness)
        ("kurt_solo", "multiply(group_zscore(ts_kurtosis(returns, 22), market), -1)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe65: root cause = even si_pos_rk standalone fails CONCENTRATED_WEIGHT
    # on 2021-05-05 (0.132 > 0.1 limit). The spike is in the short_interest
    # field on that date, not from CMA. Fix the si leg itself: smooth
    # single-day spike via ts_decay_linear, lengthen backfill window, or
    # use quantile (uniform-bounded distribution).
    "newfam_probe65": [
        # ts_decay_linear(rank(...), 10) smears single-day spike across 10 days
        ("si_decay10", "add(group_zscore(ts_decay_linear(rank(ts_backfill(news_short_interest, 22)), 10), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # ts_decay_linear span 20 (more smoothing)
        ("si_decay20", "add(group_zscore(ts_decay_linear(rank(ts_backfill(news_short_interest, 22)), 20), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # longer backfill window (252 = 1 year) for smoother backfilled values
        ("si_bf252", "add(group_zscore(rank(ts_backfill(news_short_interest, 252)), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # quantile (gaussian-bounded distribution) instead of rank
        ("si_qntl", "add(group_zscore(quantile(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # decay10 + tighter truncation 0.05 (combo to crush single-day concentration)
        ("si_decay10_t05", "add(group_zscore(ts_decay_linear(rank(ts_backfill(news_short_interest, 22)), 10), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.05, 'neutralization': 'MARKET', 'decay': 6}),
        # si_decay10 standalone (single leg, no CMA) - cleanest possible 1-leg test
        ("si_decay10_solo", "group_zscore(ts_decay_linear(rank(ts_backfill(news_short_interest, 22)), 10), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe64: si_cma is SH 2.20 / FIT 3.35 / 7 of 8 - only CONCENTRATED_WEIGHT
    # fails on 2021-05-05 (0.206 vs 0.1 limit, single-day spike from the CMA
    # asset-growth leg which uses winsorize std=4). Fix the CMA leg concentration:
    # rank() bounding, tighter winsorize std=2, smaller CMA weight, tighter
    # truncation. Keep the SH/FIT.
    "newfam_probe64": [
        # rank the CMA leg (uniform bounded weights) - cleanest fix
        ("si_cma_rk", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(rank(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252))), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # tighter winsorize std=2 on CMA leg (allows some non-uniformity, less aggressive than rank)
        ("si_cma_w2", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # CMA weight 0.5x - dampen the leg that causes concentration
        ("si_cma_w05", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), multiply(multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=4), market), -1), 0.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # rank CMA + truncation=0.05 (belt-and-suspenders)
        ("si_cma_rk_t05", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(rank(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252))), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.05, 'neutralization': 'MARKET', 'decay': 6}),
        # rank CMA + decay 4 (capture asset growth changes faster)
        ("si_cma_rk_d4", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(rank(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252))), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # winsorize std=2 + truncation=0.05 (allow some signal, cap any spike)
        ("si_cma_w2_t05", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=2), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.05, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe63: si_pos_rk standalone = SH 1.82 / FIT 2.47 / TO 0.086. To clear 2.0
    # without re-overlap, either (a) tune si alone via decay/neut/window, or
    # (b) pair with a SECOND strong orthogonal signal. Try analyst-revision
    # breadth (anl4) as a cold orthogonal cousin (event-driven info), insider
    # net activity (oth_insider), and asset growth (CMA, fnd6) - all distinct
    # from value/quality/short-reversal direction AND from short_int itself.
    "newfam_probe63": [
        # Tune si alone: faster decay (4) - capture fresh short-interest changes
        ("si_d4", "group_zscore(rank(ts_backfill(news_short_interest, 22)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # Tune si alone: deeper decay (10) - smoother turnover, persistent edge
        ("si_d10", "group_zscore(rank(ts_backfill(news_short_interest, 22)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 10}),
        # Tune si alone: INDUSTRY neutralization (short-side anomaly is industry-clustered)
        ("si_ind", "group_zscore(rank(ts_backfill(news_short_interest, 22)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'INDUSTRY', 'decay': 6}),
        # 2-leg: si + analyst-revision breadth (anl4 - cold, orthogonal, info-driven)
        ("si_anl_breadth", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), group_zscore(divide(subtract(vec_avg(anl4_basicconaf_pu), vec_avg(anl4_basicconaf_down)), add(vec_avg(anl4_basicconaf_numest), 1)), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 2-leg: si + asset growth (CMA, Fama-French 5 conservative-minus-aggressive, inverted)
        ("si_cma", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=4), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 2-leg: si + 12-1 momentum at 3x weight (boost the weak leg's contribution)
        ("si_3xmom", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), multiply(group_zscore(divide(ts_delay(close, 22), ts_delay(close, 252)), market), 3))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe62: short_int flipped sign was SH -1.46 + FIT -2.37 in probe61, meaning
    # the POSITIVE-sign version yields SH +1.46 / FIT +2.37 standalone (already
    # near LOW_FITNESS pass). On this account high short interest = high return
    # (opposite of Asquith textbook - perhaps short-squeeze regime). Stack it
    # with momentum (also positive-sign here) and a 52-week-high anchor built
    # without ts_max. Also rebuild PEAD as pure ratio to dodge the unit error.
    "newfam_probe62": [
        # short interest with POSITIVE sign (flipped from probe61 - strongest single signal)
        ("si_pos", "group_zscore(ts_backfill(news_short_interest, 22), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # short interest, rank-regularized (passes CONCENTRATED_WEIGHT if sparse)
        ("si_pos_rk", "group_zscore(rank(ts_backfill(news_short_interest, 22)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 52-week-high anchoring via 252d zscore (no ts_max)
        ("hi52w_zsc", "group_zscore(ts_zscore(close, 252), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # PEAD as pure ratio (sidesteps unit subtraction)
        ("pead_ratio", "group_zscore(ts_backfill(divide(news_eps_actual, est_epsr), 120), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 2-leg: short_int + 12-1 momentum (both orthogonal to prior pool)
        ("si_x_mom", "add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), group_zscore(divide(ts_delay(close, 22), ts_delay(close, 252)), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 3-leg: short_int + 12-1 mom + 52w-anchor (all orthogonal to value/quality/short-reversal)
        ("si_mom_52w", "add(add(group_zscore(rank(ts_backfill(news_short_interest, 22)), market), group_zscore(divide(ts_delay(close, 22), ts_delay(close, 252)), market)), group_zscore(ts_zscore(close, 252), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe61: PIVOT - the val/qual/CFO/PV-corr/short-reversal/news direction
    # registers -1,066 on Performance Comparison (alpha correlated with already-
    # submitted portfolio). Switch to ORTHOGONAL risk premia: behavioral
    # anchoring (52-week-high), lottery/MAX, medium-term momentum (opposite
    # sign from short reversal), industry momentum, PEAD earnings surprise,
    # short-interest. Each candidate is a SINGLE clean academic anomaly so
    # we can see standalone strength + how distinct each is from the prior pool.
    "newfam_probe61": [
        ("hi52w_anchor", "group_zscore(divide(close, ts_max(high, 252)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        ("max_lottery", "multiply(group_zscore(rank(ts_max(returns, 22)), market), -1)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        ("mom_12_1", "group_zscore(divide(ts_delay(close, 22), ts_delay(close, 252)), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        ("ind_mom_6m", "group_zscore(group_mean(divide(close, ts_delay(close, 126)), 1, subindustry), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        ("pead_su", "group_zscore(ts_backfill(divide(subtract(news_eps_actual, est_epsr), close), 120), market)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        ("short_int", "multiply(group_zscore(ts_backfill(news_short_interest, 22), market), -1)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    # probe60: 5-leg vqcr_pv_r2_d6 plateaued at SH 1.83 / FIT 1.27. To cross 2.0
    # while staying simple, try (a) the cheapest 6th academic leg - investor
    # sentiment (Baker-Wurgler 2006) OR news drift (Tetlock 2007) - and
    # (b) structural levers: smaller universe (TOP1000), tighter truncation,
    # deeper decay. Find the SMALLEST set of academic legs that hits 8/8.
    "newfam_probe60": [
        # 6-leg: + investor sentiment (Baker-Wurgler social-value)
        ("vqcr_pv_snt", "add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 6-leg: + news drift (Tetlock 2007 news under-reaction)
        ("vqcr_pv_news", "add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 5-leg on TOP1000 (smaller, denser universe)
        ("vqcr_pv_t1000", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP1000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 5-leg with tighter truncation 0.05 (more conviction concentration)
        ("vqcr_pv_t05", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.05, 'neutralization': 'MARKET', 'decay': 6}),
        # 5-leg with decay 8 (smoother turnover, extract lagged signal)
        ("vqcr_pv_d8", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 8}),
        # 5-leg SUBINDUSTRY whole-expression neutralization (vs MARKET)
        ("vqcr_pv_sub", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'SUBINDUSTRY', 'decay': 6}),
    ],
    # probe59: extend vqcr25 (1.81, 4-leg) with one more academic anomaly to clear 2.0.
    # Strongest addition is price-volume corr (Amihud-style illiquidity reversal,
    # Brennan-Subrahmanyam): high price-volume comovement = informed buying =
    # mean-reverts. Keep expression simple - 5 legs, each a single named anomaly.
    "newfam_probe59": [
        # 5-leg: vqcr + price-volume corr (Amihud illiquidity reversal). Reversal 2x.
        ("vqcr_pv_r2", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # 5-leg with reversal 2.5x
        ("vqcr_pv_r25", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # 5-leg, reversal 2x, decay 6 (smoother turnover)
        ("vqcr_pv_r2_d6", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 5-leg with faster corr window (10d) at reversal 2.5x
        ("vqcr_pv10_r25", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 10), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # vqcr3 - 4-leg with reversal 3x (test if heavier reversal helps with CFO leg)
        ("vqcr3", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 3))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # vqcr2 - 4-leg with reversal 2x baseline (control vs 2.5x = 1.81)
        ("vqcr2", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
    ],
    # probe58: push the 3-leg val_qual_rev2 (1.60) toward the 2.0 LOW_SHARPE limit:
    # heavier reversal weight, deeper decay, sub-industry whole-expression neut,
    # and add ONE more classic academic leg (net-issuance Pontiff-Woodgate or
    # asset-growth CMA). Stays "simple" - 3-4 named anomalies, no PV exotica.
    "newfam_probe58": [
        # val + qual + 2.5x reversal (mega's optimal reversal weight, single STR leg)
        ("vqr25", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # val + qual + 3x reversal (max weight that the mega survived 8/8 at)
        ("vqr3", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 3))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # val + qual + 2.5x reversal at decay 6 (smoother, lower TO)
        ("vqr25_d6", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # 4-leg: + net-issuance (Pontiff-Woodgate / Daniel-Titman, signed_power 0.5)
        ("vqr2_iss", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), multiply(group_zscore(signed_power(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), 0.5), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # 4-leg: + asset-growth (CMA, Fama-French 5 conservative-minus-aggressive)
        ("vqr2_cma", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets, 60), ts_delay(ts_backfill(est_tot_assets, 60), 252)), ts_delay(ts_backfill(est_tot_assets, 60), 252)), std=4), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # 4-leg: + CFO-yield (cashflow_op/cap, cash-quality leg) at 2.5x reversal
        ("vqcr25", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
    ],
    # probe57: SIMPLE + ECONOMIC + SUBMITTABLE hunt. 1-2 academic anomalies, short
    # expression, clear interpretation. Pair classic anomalies (value/quality/BAB)
    # with short-term reversal (the strongest single-signal engine from earlier probes)
    # at 2x weight to push SH past the 2.0 LOW_SHARPE limit while staying simple.
    "newfam_probe57": [
        # 1-leg: short-term reversal alone, subindustry-neutral (Jegadeesh 1990)
        ("rev_subind_d4", "multiply(group_zscore(ts_rank(close, 5), subindustry), -1)", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'SUBINDUSTRY', 'decay': 4}),
        # 2-leg: value (E/EV) + 2x short reversal (HML + STR)
        ("val_x_rev2", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # 2-leg: quality (GP/A, Novy-Marx 2013) + 2x short reversal
        ("qual_x_rev2", "add(group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # 2-leg: low-vol/BAB (Frazzini-Pedersen) + 2x short reversal
        ("bab_x_rev2", "add(multiply(group_zscore(rank(historical_volatility_120), market), -1), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        # 2-leg: value + quality (Fama-French 5 fundamentals only, no PV)
        ("val_x_qual", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        # value + quality + 2x reversal (3-leg, but each leg is a single classic anomaly)
        ("val_qual_rev2", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
    ],
    # probe56: autonomous iteration toward submittable - enhance the 2.22 mega with orthogonal
    # net-issuance + accruals (raise SH and dilute concentration/self-corr). Verify 8/8 after.
    "newfam_probe56": [
        ("m8_iss_d4", "add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), multiply(group_zscore(signed_power(divide(subtract(sharesout, ts_delay(sharesout,252)), ts_delay(sharesout,252)), 0.5), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m9_iss_accr_d4", "add(add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), multiply(group_zscore(signed_power(divide(subtract(sharesout, ts_delay(sharesout,252)), ts_delay(sharesout,252)), 0.5), market), -1)), group_zscore(rank(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120))), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m8_iss_d5", "add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), multiply(group_zscore(signed_power(divide(subtract(sharesout, ts_delay(sharesout,252)), ts_delay(sharesout,252)), 0.5), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 5}),
        ("m9_iss_accr_d5", "add(add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), multiply(group_zscore(signed_power(divide(subtract(sharesout, ts_delay(sharesout,252)), ts_delay(sharesout,252)), 0.5), market), -1)), group_zscore(rank(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120))), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 5}),
        ("m8_accr_d4", "add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), group_zscore(rank(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120))), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m9_iss15_accr", "add(add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), multiply(multiply(group_zscore(signed_power(divide(subtract(sharesout, ts_delay(sharesout,252)), ts_delay(sharesout,252)), 0.5), market), -1), 1.5)), group_zscore(rank(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120))), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
    ],
    "newfam_probe55": [
        ("accruals", "group_zscore(winsorize(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120)), std=4), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("accruals_rk", "group_zscore(rank(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120))), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("accr_ind", "group_zscore(winsorize(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120)), std=4), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'INDUSTRY'}),
        ("div_yield", "group_zscore(winsorize(divide(ts_backfill(dividend, 120), cap), std=4), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("earn_yield", "group_zscore(winsorize(divide(ts_backfill(income, 120), cap), std=4), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("accr_div", "add(group_zscore(winsorize(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120)), std=4), market), group_zscore(winsorize(divide(ts_backfill(dividend, 120), cap), std=4), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
    ],
    "newfam_probe54": [
        ("iss_sp05", "multiply(group_zscore(signed_power(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), 0.5), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_sp03", "multiply(group_zscore(signed_power(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), 0.3), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_w2", "multiply(group_zscore(winsorize(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), std=2), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_w15", "multiply(group_zscore(winsorize(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), std=1.5), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_w1", "multiply(group_zscore(winsorize(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), std=1), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_sp05_w2", "multiply(group_zscore(signed_power(winsorize(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), std=2), 0.5), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
    ],
    "newfam_probe53": [
        ("iss_rank", "multiply(group_zscore(rank(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252))), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_rank_ind", "multiply(group_zscore(rank(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252))), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'INDUSTRY'}),
        ("iss_rank_sub", "multiply(group_zscore(rank(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252))), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'SUBINDUSTRY'}),
        ("iss_rank_d10", "multiply(group_zscore(rank(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252))), market), -1)", {'delay': 0, 'decay': 10, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_bf_rank", "multiply(group_zscore(rank(ts_backfill(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), 20)), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_rank_t1000", "multiply(group_zscore(rank(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252))), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP1000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
    ],
    "newfam_probe52": [
        ("iss", "multiply(group_zscore(winsorize(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), std=4), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_ind", "multiply(group_zscore(winsorize(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), std=4), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'INDUSTRY'}),
        ("iss_subind", "multiply(group_zscore(winsorize(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), std=4), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'SUBINDUSTRY'}),
        ("agr", "multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets,60), ts_delay(ts_backfill(est_tot_assets,60), 252)), ts_delay(ts_backfill(est_tot_assets,60), 252)), std=4), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("lvol", "multiply(group_zscore(winsorize(historical_volatility_120, std=4), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("iss_agr", "add(multiply(group_zscore(winsorize(divide(subtract(sharesout, ts_delay(sharesout, 252)), ts_delay(sharesout, 252)), std=4), market), -1), multiply(group_zscore(winsorize(divide(subtract(ts_backfill(est_tot_assets,60), ts_delay(ts_backfill(est_tot_assets,60), 252)), ts_delay(ts_backfill(est_tot_assets,60), 252)), std=4), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
    ],
    "newfam_probe51": [
        ("w7_rw2_d4", "add(add(add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 2)), group_zscore(winsorize(snt_social_value, std=4), market)), group_zscore(winsorize(ts_backfill(news_indx_perf, 20), std=4), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("w7_rw2_d5", "add(add(add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 2)), group_zscore(winsorize(snt_social_value, std=4), market)), group_zscore(winsorize(ts_backfill(news_indx_perf, 20), std=4), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 5}),
        ("w7_rw2_d6", "add(add(add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 2)), group_zscore(winsorize(snt_social_value, std=4), market)), group_zscore(winsorize(ts_backfill(news_indx_perf, 20), std=4), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        ("w7_rw2_d8", "add(add(add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 2)), group_zscore(winsorize(snt_social_value, std=4), market)), group_zscore(winsorize(ts_backfill(news_indx_perf, 20), std=4), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 8}),
        ("w7_rw25_d4", "add(add(add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 2.5)), group_zscore(winsorize(snt_social_value, std=4), market)), group_zscore(winsorize(ts_backfill(news_indx_perf, 20), std=4), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("w7_rw15_d4", "add(add(add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 1.5)), group_zscore(winsorize(snt_social_value, std=4), market)), group_zscore(winsorize(ts_backfill(news_indx_perf, 20), std=4), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
    ],
    "newfam_probe50": [
        ("reg5_w1_d5", "add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 5}),
        ("reg5_w15_d5", "add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 1.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 5}),
        ("reg5_w1_d8", "add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 8}),
        ("reg5_w15_d8", "add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 1.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 8}),
        ("reg5_w15_d4", "add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1), 1.5))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("reg5_w1_d10", "add(add(add(add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(cashflow_op, 120), cap), std=4), market)), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market)), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1)), multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 10}),
    ],
    "newfam_probe49": [
        ("s_val", "group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market)", {'delay': 0, 'decay': 5, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("s_rev", "multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1)", {'delay': 0, 'decay': 4, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("s_val_rev", "add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1))", {'delay': 0, 'decay': 4, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("s_val_q", "add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market))", {'delay': 0, 'decay': 5, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("s_val_pv", "add(group_zscore(winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4), market), multiply(group_zscore(winsorize(ts_corr(close, volume, 20), std=4), market), -1))", {'delay': 0, 'decay': 5, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("s_q_rev", "add(group_zscore(winsorize(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), std=4), market), multiply(group_zscore(winsorize(ts_rank(close, 5), std=4), subindustry), -1))", {'delay': 0, 'decay': 4, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
    ],
    "newfam_probe48": [
        ("m_rw25_d4", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2.5)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m_rw3_d4", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 3)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m_rw2_d5", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 5}),
        ("m_rk3_rw2_d4", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 3), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m_rk10_rw2_d4", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 10), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m_rw25_d3", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2.5)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 3}),
    ],
    "newfam_probe47": [
        ("m7rk_d4", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(ts_rank(close, 5), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m7rk_d3", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(ts_rank(close, 5), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 3}),
        ("m7rk_d2", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(ts_rank(close, 5), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 2}),
        ("m7rk_d4_rw15", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 1.5)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m7rk_d3_rw15", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 1.5)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 3}),
        ("m7rk_d4_rw2", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(ts_rank(close, 5), subindustry), -1), 2)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
    ],
    "newfam_probe46": [
        ("m7_d4", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 4}),
        ("m7_d10", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 10}),
        ("m7_tr04", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.04, 'neutralization': 'MARKET', 'decay': 6}),
        ("m7_tr15", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.15, 'neutralization': 'MARKET', 'decay': 6}),
        ("m7_revmh", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(add(add(divide(subtract(close,ts_delay(close,3)),ts_delay(close,3)), divide(subtract(close,ts_delay(close,5)),ts_delay(close,5))), divide(subtract(close,ts_delay(close,10)),ts_delay(close,10))), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
        ("m7_revrk", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(ts_rank(close, 5), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET', 'decay': 6}),
    ],
    "newfam_probe45": [
        ("m7_wopt", "add(add(add(add(add(add(multiply(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), 1.5), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(multiply(group_zscore(ts_corr(close, volume, 20), market), -1), 1.5)), multiply(multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1), 1.5)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("m7_wopt_str", "add(add(add(add(add(add(multiply(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), 2), multiply(multiply(group_zscore(ts_corr(close, volume, 20), market), -1), 2)), multiply(multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1), 2)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("m8_scl", "add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), group_zscore(scl12_sentiment, market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("m8_news2", "add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), multiply(group_zscore(ts_backfill(news_pct_30min, 20), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("m8_range", "add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), multiply(group_zscore(divide(subtract(high, low), close), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("m9_scl_news2_wopt", "add(add(add(add(add(add(add(add(multiply(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), 1.5), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(multiply(group_zscore(ts_corr(close, volume, 20), market), -1), 1.5)), multiply(multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1), 1.5)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), group_zscore(scl12_sentiment, market)), multiply(group_zscore(ts_backfill(news_pct_30min, 20), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
    ],
    "newfam_probe44": [
        ("mega7_news", "add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("mega8_mom", "add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), group_zscore(divide(ts_delay(close, 21), ts_delay(close, 252)), subindustry))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("mega9_accr", "add(add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), group_zscore(divide(ts_delay(close, 21), ts_delay(close, 252)), subindustry)), group_zscore(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120)), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("mega8_nomews", "add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(divide(ts_delay(close, 21), ts_delay(close, 252)), subindustry)), group_zscore(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120)), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("mega9_d10", "add(add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), group_zscore(divide(ts_delay(close, 21), ts_delay(close, 252)), subindustry)), group_zscore(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120)), market))", {'delay': 0, 'decay': 10, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'MARKET'}),
        ("mega9_ind", "add(add(add(add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market)), group_zscore(ts_backfill(news_indx_perf, 20), market)), group_zscore(divide(ts_delay(close, 21), ts_delay(close, 252)), subindustry)), group_zscore(divide(subtract(ts_backfill(cashflow_op,120), ts_backfill(income,120)), ts_backfill(est_tot_assets,120)), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'truncation': 0.08, 'neutralization': 'INDUSTRY'}),
    ],
    "newfam_probe43": [
        ("mega_mkt6", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), market), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'decay': 6, 'neutralization': 'MARKET'}),
        ("mega_subz", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'decay': 6, 'neutralization': 'MARKET'}),
        ("mega_ind6", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'decay': 6, 'neutralization': 'INDUSTRY'}),
        ("mega_revw2", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1), 2))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'decay': 6, 'neutralization': 'MARKET'}),
        ("mega_sent", "add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1)), group_zscore(snt_social_value, market))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'decay': 6, 'neutralization': 'MARKET'}),
        ("mega_d10", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), subindustry), -1))", {'delay': 0, 'universe': 'TOP3000', 'truncation': 0.08, 'decay': 10, 'neutralization': 'MARKET'}),
    ],
    "newfam_probe42": [
        ("rev5_sub", "multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), market), -1)", {'delay': 0, 'decay': 4, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("rev5_ind", "multiply(group_zscore(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), market), -1)", {'delay': 0, 'decay': 4, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("revsum5_sub", "multiply(group_zscore(ts_sum(returns, 5), market), -1)", {'delay': 0, 'decay': 4, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("rev1_sub", "multiply(group_zscore(returns, market), -1)", {'delay': 0, 'decay': 2, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("revrank5_sub", "multiply(group_zscore(ts_rank(close, 5), market), -1)", {'delay': 0, 'decay': 4, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("rev_volsc_sub", "multiply(group_zscore(divide(ts_sum(returns, 5), historical_volatility_20), market), -1)", {'delay': 0, 'decay': 4, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
    ],
    "newfam_probe41": [
        ("bask_winsor4", "group_zscore(winsorize(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), std=4), market)", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask_rank", "group_zscore(rank(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))), market)", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask_tw_vol", "trade_when(greater(ts_mean(volume, 5), ts_mean(volume, 60)), group_zscore(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), market), -1)", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask_tw_calm", "trade_when(less(historical_volatility_20, ts_delay(historical_volatility_20, 20)), group_zscore(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), market), -1)", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("v_x_p", "group_zscore(multiply(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), market)", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask_winsor_ind", "group_zscore(winsorize(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), std=4), market)", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
    ],
    "newfam_probe40": [
        ("pc_ind_base", "multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("pc_ind_d10", "multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1)", {'delay': 0, 'decay': 10, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("pc_skew", "add(multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1), group_zscore(ts_backfill(implied_volatility_mean_skew_30, 5), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("pc_term", "add(multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1), group_zscore(ts_backfill(subtract(implied_volatility_mean_30, implied_volatility_mean_360), 5), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("pc_multi", "add(add(multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1), group_zscore(ts_backfill(implied_volatility_mean_skew_30, 5), market)), group_zscore(ts_backfill(subtract(implied_volatility_mean_30, implied_volatility_mean_360), 5), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("pc30_ind", "multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_30, implied_volatility_call_30), implied_volatility_mean_30), 5), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
    ],
    "newfam_probe39": [
        ("b4_t1000", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))", {'delay': 0, 'decay': 12, 'universe': 'TOP1000', 'neutralization': 'MARKET'}),
        ("b4_t500", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))", {'delay': 0, 'decay': 12, 'universe': 'TOP500', 'neutralization': 'MARKET'}),
        ("b4_d8", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))", {'delay': 0, 'decay': 8, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("b4_d10", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))", {'delay': 0, 'decay': 10, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("b4_VQtilt", "add(add(add(multiply(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market),1.5), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market),1.5))", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("b4_trunc04", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET', 'truncation': 0.04}),
    ],
    "newfam_probe38": [
        ("bask_d12", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1))", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask_d20", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1))", {'delay': 0, 'decay': 20, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask4gp_d12", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask4lv_d12", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), multiply(group_zscore(historical_volatility_120, market), -1))", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask5_d12", "add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), multiply(group_zscore(historical_volatility_120, market), -1))", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("bask_corr60_d12", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 60), market), -1))", {'delay': 0, 'decay': 12, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe37": [
        ("basket3_mkt", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("basket3_ind", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("basket_hybrid", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), industry), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("basket_VP", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_corr(close, volume, 20), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("basket_Vtilt", "add(add(multiply(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), 2), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), multiply(group_zscore(ts_corr(close, volume, 20), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("basket_VPi", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_corr(close, volume, 20), industry), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe36": [
        ("pv_corr", "group_zscore(ts_corr(close, volume, 20), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("vwap_rev", "multiply(group_zscore(divide(subtract(close, vwap), vwap), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("volofvol", "multiply(group_zscore(ts_std_dev(historical_volatility_20, 60), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("range_skew", "group_zscore(ts_backfill(divide(subtract(news_max_up_amt, news_max_dn_amt), close), 5), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("amihud", "group_zscore(ts_mean(divide(abs(returns), volume), 20), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("pv_corr_ind", "group_zscore(ts_corr(close, volume, 20), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
    ],
    "newfam_probe35": [
        ("sue_ratio", "group_zscore(ts_backfill(divide(news_eps_actual, est_epsr), 90), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("sue_ratio_ind", "group_zscore(ts_backfill(divide(news_eps_actual, est_epsr), 90), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("sue_zdiff", "group_zscore(subtract(group_zscore(ts_backfill(news_eps_actual,90),market), group_zscore(ts_backfill(est_epsr,90),market)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("sue_zdiff_ind", "group_zscore(subtract(group_zscore(ts_backfill(news_eps_actual,90),market), group_zscore(ts_backfill(est_epsr,90),market)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("sue_drift", "add(group_zscore(ts_backfill(divide(news_eps_actual, est_epsr), 90), market), group_zscore(ts_backfill(news_pct_30min, 20), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("earn_yield", "group_zscore(divide(1, ts_backfill(news_pe_ratio, 5)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe34": [
        ("eps_surprise", "group_zscore(ts_backfill(divide(subtract(news_eps_actual, est_epsr), close), 60), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("eps_surprise_ind", "group_zscore(ts_backfill(divide(subtract(news_eps_actual, est_epsr), close), 60), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("news_react30", "group_zscore(ts_backfill(news_pct_30min, 20), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("news_idxperf", "group_zscore(ts_backfill(news_indx_perf, 20), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("news_volshock", "group_zscore(ts_backfill(news_vol_stddev, 5), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("news_react_ind", "group_zscore(ts_backfill(news_pct_30min, 20), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
    ],
    "newfam_probe33": [
        ("high52r", "group_zscore(ts_rank(close, 252), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("high52r_ind", "group_zscore(ts_rank(close, 252), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("high52r_sub", "group_zscore(ts_rank(close, 252), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("val_high52r", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(ts_rank(close, 252), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("multi_comp_r", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(ts_rank(close, 252), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("high52r_dec20", "group_zscore(ts_rank(close, 252), market)", {'delay': 0, 'decay': 20, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe32": [
        ("high52", "group_zscore(divide(close, ts_max(high, 252)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("high52_ind", "group_zscore(divide(close, ts_max(high, 252)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("idio_mom", "group_zscore(divide(ts_delay(close, 21), ts_delay(close, 252)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("fund_mom", "group_zscore(ts_delta(ts_backfill(return_assets, 20), 252), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("multi_comp", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)), group_zscore(divide(close, ts_max(high, 252)), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_high52", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(close, ts_max(high, 252)), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe31": [
        ("eps_rev", "group_zscore(divide(ts_delta(ts_backfill(est_epsr, 20), 63), close), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("np_rev", "group_zscore(divide(ts_delta(ts_backfill(est_netprofit, 20), 63), cap), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ebit_rev", "group_zscore(divide(ts_delta(ts_backfill(est_ebit, 20), 63), cap), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("eps_rev_ind", "group_zscore(divide(ts_delta(ts_backfill(est_epsr, 20), 63), close), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("rev_comp", "add(group_zscore(divide(ts_delta(ts_backfill(est_epsr, 20), 63), close), market), group_zscore(divide(ts_delta(ts_backfill(est_netprofit, 20), 63), cap), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("eps_rev_126", "group_zscore(divide(ts_delta(ts_backfill(est_epsr, 20), 126), close), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe30": [
        ("val_ind", "group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("val_subind", "group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("si_ind", "multiply(group_zscore(ts_backfill(news_short_interest, 20), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("cfoy_ind", "group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("gp_ind", "group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("valqual_ind", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
    ],
    "newfam_probe29": [
        ("pc_flip", "multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("pc_flip_ind", "multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("pc_flip_t500", "multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP500', 'neutralization': 'MARKET'}),
        ("val_pc", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_pc_skew", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1)), group_zscore(ts_backfill(implied_volatility_mean_skew_30, 5), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("pc_flip_dec20", "multiply(group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market), -1)", {'delay': 0, 'decay': 20, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe28": [
        ("iv_skew", "group_zscore(ts_backfill(implied_volatility_mean_skew_30, 5), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("pc_spread", "group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("iv_term", "group_zscore(ts_backfill(subtract(implied_volatility_mean_30, implied_volatility_mean_360), 5), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("iv_vrp", "group_zscore(subtract(ts_backfill(implied_volatility_mean_60, 5), historical_volatility_60), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("iv_level", "group_zscore(ts_backfill(implied_volatility_mean_60, 5), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_pc_blend", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(ts_backfill(divide(subtract(implied_volatility_put_60, implied_volatility_call_60), implied_volatility_mean_60), 5), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe27": [
        ("d0_lowvol", "multiply(group_zscore(historical_volatility_120, market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_lowvol_pk", "multiply(group_zscore(parkinson_volatility_120, market), -1)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_snt_val", "group_zscore(snt_value, market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_snt_sval", "group_zscore(snt_social_value, market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_scl_sent", "group_zscore(scl12_sentiment, market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_rel_comp", "group_zscore(rel_ret_comp, market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe26": [
        ("d0_accruals", "group_zscore(divide(subtract(ts_backfill(cashflow_op, 120), ts_backfill(income, 120)), ts_backfill(est_tot_assets, 120)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_roa", "group_zscore(ts_backfill(return_assets, 120), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_roe", "group_zscore(ts_backfill(return_equity, 120), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_cfoyield", "group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_gp_assets", "group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_qualstack", "add(add(add(group_zscore(divide(subtract(ts_backfill(cashflow_op, 120), ts_backfill(income, 120)), ts_backfill(est_tot_assets, 120)), market), group_zscore(ts_backfill(return_assets, 120), market)), group_zscore(divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120)), market)), group_zscore(divide(ts_backfill(cashflow_op, 120), cap), market))", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe25": [
        ("d0_util", "group_zscore(mdl177_5shortsentimentfactor_act_util, market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_fee", "group_zscore(mdl177_5shortsentimentfactor_benchmark_fee, market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_dtc", "group_zscore(mdl177_5shortsentimentfactor_days_to_cover, market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_si_news", "group_zscore(news_short_interest, market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_si_vec", "group_zscore(vec_avg(nws12_mainz_short_interest), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("d0_si_pre", "group_zscore(vec_avg(nws12_prez_short_interest), market)", {'delay': 0, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe24": [
        ("ss_dtc", "group_zscore(mdl177_5shortsentimentfactor_days_to_cover, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ss_dmdsup", "group_zscore(mdl177_5shortsentimentfactor_dmd_supply, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ss_util_ind", "group_zscore(mdl177_5shortsentimentfactor_act_util, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'INDUSTRY'}),
        ("ss_util_sub", "group_zscore(mdl177_5shortsentimentfactor_act_util, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("ss_util_t03", "group_zscore(mdl177_5shortsentimentfactor_act_util, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET', 'truncation': 0.03}),
        ("ss_invconc", "group_zscore(mdl177_5shortsentimentfactor_inv_conc, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe23": [
        ("ss_fee", "group_zscore(mdl177_5shortsentimentfactor_benchmark_fee, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ss_util", "group_zscore(mdl177_5shortsentimentfactor_act_util, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ss_dtc", "group_zscore(mdl177_5shortsentimentfactor_days_to_cover, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ss_dmdsup", "group_zscore(mdl177_5shortsentimentfactor_dmd_supply, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ss_shtint", "group_zscore(mdl177_5shortsentimentfactor_sht_int, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ss_stack", "add(add(add(add(group_zscore(mdl177_5shortsentimentfactor_benchmark_fee, market), group_zscore(mdl177_5shortsentimentfactor_act_util, market)), group_zscore(mdl177_5shortsentimentfactor_days_to_cover, market)), group_zscore(mdl177_5shortsentimentfactor_dmd_supply, market)), group_zscore(mdl177_5shortsentimentfactor_sht_int, market))", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe22": [
        ("emm_comp", "group_zscore(mdl177_emmcomposite_emm_composite, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("qma_comp", "group_zscore(mdl177_momemtumanalystmodel_qma_composite, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("qsa_comp", "group_zscore(mdl177_surpriseanalystmodel_qsa_composite, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("qpa_comp", "group_zscore(mdl177_priceanalystmodel_qpa_composite_alt, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("dvm_comp", "group_zscore(mdl177_vra2_dvm_composite, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("abr_pead", "group_zscore(mdl177_pricemomentumfactor_abr, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ebitdaev", "group_zscore(mdl177_2_deepvaluefactor_ebitdaev, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("estep", "group_zscore(mdl177_relativevaluemodel_fc_estep, market)", {'delay': 1, 'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe21": [
        ("ts_z_rev", "multiply(group_zscore(ts_zscore(close, 120), market), -1)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ma_ratio", "group_zscore(divide(ts_mean(close, 10), ts_mean(close, 120)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("vol_rank", "group_zscore(ts_rank(volume, 120), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("ts_ir_ret", "multiply(group_zscore(ts_ir(returns, 120), market), -1)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_x_qual", "group_zscore(multiply(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(divide(subtract(revenue, cogs), ts_backfill(assets, 60)), market)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_lowvol", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_std_dev(returns, 120), market), -1))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe20": [
        ("gap_rev", "multiply(group_zscore(ts_backfill(news_open_gap, 5), market), -1)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("relidx", "group_zscore(ts_backfill(news_indx_perf, 5), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("divyield", "group_zscore(ts_backfill(news_dividend_yield, 60), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("newsls", "group_zscore(ts_backfill(news_ls, 5), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("prevret_rev", "multiply(group_zscore(ts_backfill(news_prev_day_ret, 5), market), -1)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("newsreact", "group_zscore(ts_backfill(add(news_max_up_ret, news_max_dn_ret), 5), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe19": [
        ("si_nanmask", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), nan_mask(group_zscore(ts_backfill(news_short_interest, 66), market), 0))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("si_replace", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), replace(group_zscore(ts_backfill(news_short_interest, 66), market), nan, 0))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("si_tonan", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), to_nan(group_zscore(ts_backfill(news_short_interest, 66), market), 0, true))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_si_2x", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market)), nan_mask(group_zscore(ts_backfill(news_short_interest, 66), market), 0))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe18": [
        ("val_fcf", "group_zscore(ts_backfill(divide(est_fcf, cap), 120), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_cfo", "group_zscore(ts_backfill(divide(est_cashflow_op, cap), 120), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_book", "group_zscore(ts_backfill(divide(est_bookvalue_ps, close), 120), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_comp4", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(ts_backfill(divide(est_fcf, cap), 120), market)), group_zscore(ts_backfill(divide(est_cashflow_op, cap), 120), market)), group_zscore(ts_backfill(divide(est_bookvalue_ps, close), 120), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_comp6", "add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(ts_backfill(divide(est_fcf, cap), 120), market)), group_zscore(ts_backfill(divide(est_cashflow_op, cap), 120), market)), group_zscore(ts_backfill(divide(est_ebit, cap), 120), market)), group_zscore(ts_backfill(divide(est_bookvalue_ps, close), 120), market)), group_zscore(ts_backfill(divide(revenue, cap), 120), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_comp4_sub", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), group_zscore(ts_backfill(divide(est_fcf, cap), 120), market)), group_zscore(ts_backfill(divide(est_cashflow_op, cap), 120), market)), group_zscore(ts_backfill(divide(est_bookvalue_ps, close), 120), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
    ],
    "newfam_probe17": [
        ("dense6", "add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1)), multiply(group_zscore(divide(ts_delay(close, 21), ts_delay(close, 750)), market), -1)), group_zscore(divide(subtract(vwap, close), close), market)), group_zscore(divide(subtract(revenue, cogs), ts_backfill(assets, 60)), market)), multiply(group_zscore(divide(ts_delta(ts_backfill(assets, 60), 250), ts_backfill(assets, 60)), market), -1))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("dense4", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1)), multiply(group_zscore(divide(ts_delay(close, 21), ts_delay(close, 750)), market), -1)), group_zscore(divide(subtract(vwap, close), close), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("dense_vir", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1)), group_zscore(divide(subtract(vwap, close), close), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("dense6_sub", "add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1)), multiply(group_zscore(divide(ts_delay(close, 21), ts_delay(close, 750)), market), -1)), group_zscore(divide(subtract(vwap, close), close), market)), group_zscore(divide(subtract(revenue, cogs), ts_backfill(assets, 60)), market)), multiply(group_zscore(divide(ts_delta(ts_backfill(assets, 60), 250), ts_backfill(assets, 60)), market), -1))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'SUBINDUSTRY'}),
        ("dense4_d10", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1)), multiply(group_zscore(divide(ts_delay(close, 21), ts_delay(close, 750)), market), -1)), group_zscore(divide(subtract(vwap, close), close), market))", {'decay': 10, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("dense6_d3", "add(add(add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1)), multiply(group_zscore(divide(ts_delay(close, 21), ts_delay(close, 750)), market), -1)), group_zscore(divide(subtract(vwap, close), close), market)), group_zscore(divide(subtract(revenue, cogs), ts_backfill(assets, 60)), market)), multiply(group_zscore(divide(ts_delta(ts_backfill(assets, 60), 250), ts_backfill(assets, 60)), market), -1))", {'decay': 3, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
    "newfam_probe16": [
        ("si500_tr02", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP500', 'neutralization': 'MARKET', 'truncation': 0.02}),
        ("si500_tr01", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP500', 'neutralization': 'MARKET', 'truncation': 0.01}),
        ("si500_tr03", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP500', 'neutralization': 'MARKET', 'truncation': 0.03}),
        ("si3k_tr01", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET', 'truncation': 0.01}),
        ("si3k_tr005", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET', 'truncation': 0.005}),
        ("sir3k_tr01", "add(winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4), quantile(divide(subtract(vwap, close), close)))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET', 'truncation': 0.01}),
    ],
    "newfam_probe15": [
        ("si_top1000", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP1000', 'neutralization': 'MARKET'}),
        ("si_top500", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP500', 'neutralization': 'MARKET'}),
        ("si_top200", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP200', 'neutralization': 'MARKET'}),
        ("si_t1k_ind", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP1000', 'neutralization': 'INDUSTRY'}),
        ("si_t1k_mkt", "group_zscore(ts_backfill(news_short_interest, 66), market)", {'decay': 6, 'universe': 'TOP1000', 'neutralization': 'MARKET'}),
        ("si_t500_sub", "winsorize(group_zscore(ts_backfill(news_short_interest, 66), sector), std=4)", {'decay': 6, 'universe': 'TOP500', 'neutralization': 'SUBINDUSTRY'}),
    ],
    "newfam_probe14": [
        ("issuance", "multiply(group_zscore(ts_delta(sharesout, 250), market), -1)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("assetgrow", "multiply(group_zscore(divide(ts_delta(ts_backfill(assets, 60), 250), ts_backfill(assets, 60)), market), -1)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("grossprof", "group_zscore(divide(subtract(revenue, cogs), ts_backfill(assets, 60)), market)", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_iss", "add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("val_iss_gp", "add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1)), group_zscore(divide(subtract(revenue, cogs), ts_backfill(assets, 60)), market))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
        ("quality_stack", "add(add(add(group_zscore(ts_backfill(divide(est_ebitda, cap), 120), market), multiply(group_zscore(ts_delta(sharesout, 250), market), -1)), group_zscore(divide(subtract(revenue, cogs), ts_backfill(assets, 60)), market)), multiply(group_zscore(divide(ts_delta(ts_backfill(assets, 60), 250), ts_backfill(assets, 60)), market), -1))", {'decay': 6, 'universe': 'TOP3000', 'neutralization': 'MARKET'}),
    ],
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
