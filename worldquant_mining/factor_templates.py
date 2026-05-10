"""
Factor (alpha) expression templates.

The upstream `worldquant-miner` does not ship a real template library — it
only has four trivial fallbacks (`ts_rank(close, 20)` etc.) baked into
`core/template_generator.py::_generate_fallback_template`. The miner
relies on an LLM to generate every expression from scratch.

This module fills that gap with two seed libraries:

1. **ALPHA_101** — the 101 Formulaic Alphas published by Kakushadze (2015,
   "101 Formulaic Alphas", arXiv:1601.00991, WorldQuant LLC). Each entry is
   a `(id, expression)` pair using only operators and primitive PV fields
   that exist on WorldQuant Brain. Expressions are translated into the
   Brain FASTEXPR syntax (e.g. `Ts_ArgMax` -> `ts_arg_max`,
   `IndNeutralize` -> `group_neutralize`).

2. **CLASSICAL_FACTORS** — a curated set of well-known equity factors
   (momentum, mean-reversion, low-volatility, liquidity, idiosyncratic
   volatility, etc.) expressed in the same syntax. These provide
   non-overlapping starting points the LLM/evolutionary search can mutate.

Each template entry is a dict:

    {
        "id":         str,        # stable identifier (e.g. "alpha_001")
        "name":       str,        # short human label
        "category":   str,        # momentum | reversal | volatility | ...
        "expression": str,        # FASTEXPR alpha expression
        "source":     str,        # citation
    }
"""

from __future__ import annotations

from typing import Dict, List


def _t(id_: str, name: str, category: str, expression: str,
       source: str = "Kakushadze 2015 - 101 Formulaic Alphas") -> Dict:
    return {
        "id": id_,
        "name": name,
        "category": category,
        "expression": " ".join(expression.split()),
        "source": source,
    }


# ---------------------------------------------------------------------------
# Kakushadze (2015) - "101 Formulaic Alphas"
# Translated to WorldQuant Brain FASTEXPR.
# Notation:
#   - returns / open / high / low / close / volume / vwap / cap are PV fields
#   - adv{N} = ts_mean(volume, N)
#   - rank(x)            -> rank(x)
#   - delay(x, d)        -> ts_delay(x, d)
#   - delta(x, d)        -> ts_delta(x, d)
#   - sum(x, d)          -> ts_sum(x, d)
#   - product(x, d)      -> ts_product(x, d)
#   - stddev(x, d)       -> ts_std_dev(x, d)
#   - correlation(x,y,d) -> ts_corr(x, y, d)
#   - covariance(x,y,d)  -> ts_covariance(x, y, d)
#   - scale(x)           -> scale(x)
#   - ts_min(x, d)       -> ts_min(x, d)        (similarly ts_max, ts_rank)
#   - Ts_ArgMin/ArgMax   -> ts_arg_min / ts_arg_max
#   - signedpower(x, e)  -> signed_power(x, e)
#   - decay_linear(x, d) -> ts_decay_linear(x, d)
#   - IndNeutralize(x,g) -> group_neutralize(x, g)
#   - sector / industry / subindustry are GROUP fields
# ---------------------------------------------------------------------------
ALPHA_101: List[Dict] = [
    _t("alpha_001", "rank-of-stddev-argmax", "reversal",
       "(rank(ts_arg_max(signed_power(if_else(returns < 0, ts_std_dev(returns, 20), close), 2.), 5)) - 0.5)"),
    _t("alpha_002", "neg-corr-volchg-intraday-rank", "reversal",
       "(-1 * ts_corr(rank(ts_delta(log(volume), 2)), rank(((close - open) / open)), 6))"),
    _t("alpha_003", "neg-corr-rank-open-volume", "reversal",
       "(-1 * ts_corr(rank(open), rank(volume), 10))"),
    _t("alpha_004", "ts-rank-of-rank-low", "reversal",
       "(-1 * ts_rank(rank(low), 9))"),
    _t("alpha_005", "rank-vwap-mean-rank-close-rev", "value",
       "(rank((open - (ts_sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))"),
    _t("alpha_006", "neg-corr-open-volume", "reversal",
       "(-1 * ts_corr(open, volume, 10))"),
    _t("alpha_007", "adv-vs-deltaclose", "trend",
       "if_else(adv20 < volume, ((-1 * ts_rank(abs(ts_delta(close, 7)), 60)) * sign(ts_delta(close, 7))), -1)"),
    _t("alpha_008", "rank-rolling-open-returns", "momentum",
       "(-1 * rank(((ts_sum(open, 5) * ts_sum(returns, 5)) - ts_delay((ts_sum(open, 5) * ts_sum(returns, 5)), 10))))"),
    _t("alpha_009", "trend-conditional-deltaclose", "momentum",
       "if_else(0 < ts_min(ts_delta(close, 1), 5), ts_delta(close, 1), if_else(ts_max(ts_delta(close, 1), 5) < 0, ts_delta(close, 1), (-1 * ts_delta(close, 1))))"),
    _t("alpha_010", "rank-trend-conditional-deltaclose", "momentum",
       "rank(if_else(0 < ts_min(ts_delta(close, 1), 4), ts_delta(close, 1), if_else(ts_max(ts_delta(close, 1), 4) < 0, ts_delta(close, 1), (-1 * ts_delta(close, 1)))))"),
    _t("alpha_011", "rank-vwap-close-rangedelta-volume", "value",
       "((rank(ts_max((vwap - close), 3)) + rank(ts_min((vwap - close), 3))) * rank(ts_delta(volume, 3)))"),
    _t("alpha_012", "sign-volchg-revclose", "reversal",
       "(sign(ts_delta(volume, 1)) * (-1 * ts_delta(close, 1)))"),
    _t("alpha_013", "neg-rank-cov-rank-close-volume", "reversal",
       "(-1 * rank(ts_covariance(rank(close), rank(volume), 5)))"),
    _t("alpha_014", "deltareturns-cov-open-volume", "reversal",
       "((-1 * rank(ts_delta(returns, 3))) * ts_corr(open, volume, 10))"),
    _t("alpha_015", "neg-rolling-rank-corr", "reversal",
       "(-1 * ts_sum(rank(ts_corr(rank(high), rank(volume), 3)), 3))"),
    _t("alpha_016", "neg-rank-cov-high-volume", "reversal",
       "(-1 * rank(ts_covariance(rank(high), rank(volume), 5)))"),
    _t("alpha_017", "ts-rank-vol-deltaclose", "reversal",
       "(((-1 * rank(ts_rank(close, 10))) * rank(ts_delta(ts_delta(close, 1), 1))) * rank(ts_rank((volume / adv20), 5)))"),
    _t("alpha_018", "rank-stddev-corr-closeopen", "reversal",
       "(-1 * rank(((ts_std_dev(abs((close - open)), 5) + (close - open)) + ts_corr(close, open, 10))))"),
    _t("alpha_019", "trend-with-returns-rank", "momentum",
       "((-1 * sign(((close - ts_delay(close, 7)) + ts_delta(close, 7)))) * (1 + rank((1 + ts_sum(returns, 250)))))"),
    _t("alpha_020", "rank-open-vs-prev-extreme", "reversal",
       "(((-1 * rank((open - ts_delay(high, 1)))) * rank((open - ts_delay(close, 1)))) * rank((open - ts_delay(low, 1))))"),
    _t("alpha_021", "moving-avg-vs-stddev-trend", "momentum",
       "if_else(((ts_sum(close, 8) / 8) + ts_std_dev(close, 8)) < (ts_sum(close, 2) / 2), -1, if_else((ts_sum(close, 2) / 2) < ((ts_sum(close, 8) / 8) - ts_std_dev(close, 8)), 1, if_else((1 < (volume / adv20)), 1, -1)))"),
    _t("alpha_022", "stddev-of-corr-deltaprice", "reversal",
       "(-1 * (ts_delta(ts_corr(high, volume, 5), 5) * rank(ts_std_dev(close, 20))))"),
    _t("alpha_023", "neg-deltahigh-on-trend", "reversal",
       "if_else((ts_sum(high, 20) / 20) < high, (-1 * ts_delta(high, 2)), 0)"),
    _t("alpha_024", "low-of-low-trend", "reversal",
       "if_else((ts_delta((ts_sum(close, 100) / 100), 100) / ts_delay(close, 100)) <= 0.05, (-1 * (close - ts_min(close, 100))), (-1 * ts_delta(close, 3)))"),
    _t("alpha_025", "rank-product-returns-adv-vwap", "value",
       "rank(((((-1 * returns) * adv20) * vwap) * (high - close)))"),
    _t("alpha_026", "ts-rank-corr-volume-rolledhigh", "reversal",
       "(-1 * ts_max(ts_corr(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))"),
    _t("alpha_027", "trend-from-corr-rank-volume-vwap", "momentum",
       "if_else(0.5 < rank((ts_sum(ts_corr(rank(volume), rank(vwap), 6), 2) / 2.0)), -1, 1)"),
    _t("alpha_028", "scale-corr-adv-low-mid", "reversal",
       "scale(((ts_corr(adv20, low, 5) + ((high + low) / 2)) - close))"),
    _t("alpha_029", "rank-min-prod-scale-log-tsmin", "reversal",
       "(ts_min(ts_product(rank(rank(scale(log(ts_sum(ts_min(rank(rank((-1 * rank(ts_delta((close - 1), 5))))), 2), 1))))), 1), 5) + ts_rank(ts_delay((-1 * returns), 6), 5))"),
    _t("alpha_030", "deltaclose-sign-volume-ratio", "reversal",
       "(((1.0 - rank(((sign((close - ts_delay(close, 1))) + sign((ts_delay(close, 1) - ts_delay(close, 2)))) + sign((ts_delay(close, 2) - ts_delay(close, 3)))))) * ts_sum(volume, 5)) / ts_sum(volume, 20))"),
    _t("alpha_031", "decay-rank-deltaclose-sign-corr", "reversal",
       "((rank(rank(rank(ts_decay_linear((-1 * rank(rank(ts_delta(close, 10)))), 10)))) + rank((-1 * ts_delta(close, 3)))) + sign(scale(ts_corr(adv20, low, 12))))"),
    _t("alpha_032", "scale-meanclose-corr-vwap-delaclose", "reversal",
       "(scale(((ts_sum(close, 7) / 7) - close)) + (20 * scale(ts_corr(vwap, ts_delay(close, 5), 230))))"),
    _t("alpha_033", "rank-open-over-close", "reversal",
       "rank((-1 * ((1 - (open / close)))))"),
    _t("alpha_034", "rank-stddev-and-deltaclose", "reversal",
       "rank(((1 - rank((ts_std_dev(returns, 2) / ts_std_dev(returns, 5)))) + (1 - rank(ts_delta(close, 1)))))"),
    _t("alpha_035", "ts-rank-vol-and-mid-rev", "reversal",
       "((ts_rank(volume, 32) * (1 - ts_rank(((close + high) - low), 16))) * (1 - ts_rank(returns, 32)))"),
    _t("alpha_036", "weighted-corr-features", "reversal",
       "(((((2.21 * rank(ts_corr((close - open), ts_delay(volume, 1), 15))) + (0.7 * rank((open - close)))) + (0.73 * rank(ts_rank(ts_delay((-1 * returns), 6), 5)))) + rank(abs(ts_corr(vwap, adv20, 6)))) + (0.6 * rank((((ts_sum(close, 200) / 200) - open) * (close - open)))))"),
    _t("alpha_037", "rank-corr-laggedopen-and-rangedelta", "reversal",
       "(rank(ts_corr(ts_delay((open - close), 1), close, 200)) + rank((open - close)))"),
    _t("alpha_038", "ts-rank-close-and-open", "reversal",
       "((-1 * rank(ts_rank(close, 10))) * rank((close / open)))"),
    _t("alpha_039", "rank-deltaclose-with-decay-volume-returns", "reversal",
       "((-1 * rank((ts_delta(close, 7) * (1 - rank(ts_decay_linear((volume / adv20), 9)))))) * (1 + rank(ts_sum(returns, 250))))"),
    _t("alpha_040", "rank-stddev-times-corr", "reversal",
       "((-1 * rank(ts_std_dev(high, 10))) * ts_corr(high, volume, 10))"),
    _t("alpha_041", "midprice-vs-vwap", "value",
       "(((high * low) ^ 0.5) - vwap)"),
    _t("alpha_042", "rank-vwap-close-vs-rank-vwap-plus-close", "value",
       "(rank((vwap - close)) / rank((vwap + close)))"),
    _t("alpha_043", "ts-rank-vol-and-deltaclose", "reversal",
       "(ts_rank((volume / adv20), 20) * ts_rank((-1 * ts_delta(close, 7)), 8))"),
    _t("alpha_044", "neg-corr-high-rank-volume", "reversal",
       "(-1 * ts_corr(high, rank(volume), 5))"),
    _t("alpha_045", "rank-mean-laggedclose", "reversal",
       "(-1 * ((rank((ts_sum(ts_delay(close, 5), 20) / 20)) * ts_corr(close, volume, 2)) * rank(ts_corr(ts_sum(close, 5), ts_sum(close, 20), 2))))"),
    _t("alpha_046", "trend-strength-conditional", "momentum",
       "if_else(0.25 < (((ts_delay(close, 20) - ts_delay(close, 10)) / 10) - ((ts_delay(close, 10) - close) / 10)), -1, if_else((((ts_delay(close, 20) - ts_delay(close, 10)) / 10) - ((ts_delay(close, 10) - close) / 10)) < 0, 1, (-1 * (close - ts_delay(close, 1)))))"),
    _t("alpha_047", "rank-vol-vs-adv-and-corr", "reversal",
       "((((rank((1 / close)) * volume) / adv20) * ((high * rank((high - close))) / (ts_sum(high, 5) / 5))) - rank((vwap - ts_delay(vwap, 5))))"),
    _t("alpha_048", "indneutralized-deltaclose-corr", "reversal",
       "(group_neutralize(((ts_corr(ts_delta(close, 1), ts_delta(ts_delay(close, 1), 1), 250) * ts_delta(close, 1)) / close), subindustry) / ts_sum(((ts_delta(close, 1) / ts_delay(close, 1)) ^ 2), 250))"),
    _t("alpha_049", "trend-vs-stddev", "momentum",
       "if_else((((ts_delay(close, 20) - ts_delay(close, 10)) / 10) - ((ts_delay(close, 10) - close) / 10)) < (-0.1 * 1), 1, (-1 * (close - ts_delay(close, 1))))"),
    _t("alpha_050", "neg-tsmax-rank-corr-volume-vwap", "reversal",
       "(-1 * ts_max(rank(ts_corr(rank(volume), rank(vwap), 5)), 5))"),
    _t("alpha_051", "trend-vs-stddev-2", "momentum",
       "if_else((((ts_delay(close, 20) - ts_delay(close, 10)) / 10) - ((ts_delay(close, 10) - close) / 10)) < (-1 * 0.05), 1, (-1 * (close - ts_delay(close, 1))))"),
    _t("alpha_052", "rolling-mins-with-returns-rank", "value",
       "((((-1 * ts_min(low, 5)) + ts_delay(ts_min(low, 5), 5)) * rank(((ts_sum(returns, 240) - ts_sum(returns, 20)) / 220))) * ts_rank(volume, 5))"),
    _t("alpha_053", "neg-deltaclose-vs-range", "reversal",
       "(-1 * ts_delta((((close - low) - (high - close)) / (close - low)), 9))"),
    _t("alpha_054", "open-low-vs-close-low-power", "reversal",
       "((-1 * ((low - close) * (open ^ 5))) / ((low - high) * (close ^ 5)))"),
    _t("alpha_055", "neg-corr-rank-rangepos-volume", "reversal",
       "(-1 * ts_corr(rank(((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12)))), rank(volume), 6))"),
    _t("alpha_056", "rank-cap-weighted-returns", "value",
       "(0 - (1 * (rank((ts_sum(returns, 10) / ts_sum(ts_sum(returns, 2), 3))) * rank((returns * cap)))))"),
    _t("alpha_057", "decay-rank-argmax-close-vs-vwap", "reversal",
       "(0 - (1 * ((close - vwap) / ts_decay_linear(rank(ts_arg_max(close, 30)), 2))))"),
    _t("alpha_058", "indneutral-vwap-corr", "reversal",
       "(-1 * ts_rank(ts_decay_linear(ts_corr(group_neutralize(vwap, sector), volume, 4), 8), 6))"),
    _t("alpha_059", "indneutral-vwap-blend-corr", "reversal",
       "(-1 * ts_rank(ts_decay_linear(ts_corr(group_neutralize(((vwap * 0.728317) + (vwap * (1 - 0.728317))), industry), volume, 4), 16), 8))"),
    _t("alpha_060", "scaled-rank-vs-rank-argmax", "reversal",
       "(0 - (1 * ((2 * scale(rank(((((close - low) - (high - close)) / (high - low)) * volume)))) - scale(rank(ts_arg_max(close, 10))))))"),
    _t("alpha_061", "vwap-vs-tsmin-corr-rank", "reversal",
       "(rank((vwap - ts_min(vwap, 16))) < rank(ts_corr(vwap, adv180, 18)))"),
    _t("alpha_062", "rank-corr-vwap-mean-vs-mid", "reversal",
       "((rank(ts_corr(vwap, ts_sum(adv20, 22), 10)) < rank(((rank(open) + rank(open)) < (rank(((high + low) / 2)) + rank(high))))) * -1)"),
    _t("alpha_063", "indneutral-decay-deltaclose-corr-volume", "reversal",
       "((rank(ts_decay_linear(ts_delta(group_neutralize(close, industry), 2), 8)) - rank(ts_decay_linear(ts_corr(((vwap * 0.318108) + (open * (1 - 0.318108))), ts_sum(adv180, 37), 14), 12))) * -1)"),
    _t("alpha_064", "weighted-bar-corr-rank", "reversal",
       "((rank(ts_corr(ts_sum(((open * 0.178404) + (low * (1 - 0.178404))), 13), ts_sum(adv120, 13), 17)) < rank(ts_delta(((((high + low) / 2) * 0.178404) + (vwap * (1 - 0.178404))), 4))) * -1)"),
    _t("alpha_065", "vwap-open-vs-tsmin", "reversal",
       "((rank(ts_corr(((open * 0.00817205) + (vwap * (1 - 0.00817205))), ts_sum(adv60, 9), 6)) < rank((open - ts_min(open, 14)))) * -1)"),
    _t("alpha_066", "high-low-rank-decay", "reversal",
       "((rank(ts_decay_linear(ts_delta(vwap, 4), 7)) + ts_rank(ts_decay_linear(((((low * 0.96633) + (low * (1 - 0.96633))) - vwap) / (open - ((high + low) / 2))), 11), 7)) * -1)"),
    _t("alpha_067", "indneutral-high-corr", "reversal",
       "((rank((high - ts_min(high, 2))) ^ rank(ts_corr(group_neutralize(vwap, sector), group_neutralize(adv20, subindustry), 6))) * -1)"),
    _t("alpha_068", "ts-rank-corr-rank-high-low-vs-deltaclose", "reversal",
       "((ts_rank(ts_corr(rank(high), rank(adv15), 9), 14) < rank(ts_delta(((close * 0.518371) + (low * (1 - 0.518371))), 1))) * -1)"),
    _t("alpha_069", "indneutral-deltaclose-tsrank", "reversal",
       "((rank(ts_max(ts_delta(group_neutralize(vwap, industry), 3), 5)) ^ ts_rank(ts_corr(((close * 0.490655) + (vwap * (1 - 0.490655))), adv20, 5), 9)) * -1)"),
    _t("alpha_070", "indneutral-corr-deltavwap", "reversal",
       "((rank(ts_delta(vwap, 1)) ^ ts_rank(ts_corr(group_neutralize(close, industry), adv50, 18), 18)) * -1)"),
    _t("alpha_071", "max-of-tsranks", "reversal",
       "max(ts_rank(ts_decay_linear(ts_corr(ts_rank(close, 3), ts_rank(adv180, 12), 18), 4), 16), ts_rank(ts_decay_linear((rank(((low + open) - (vwap + vwap))) ^ 2), 16), 4))"),
    _t("alpha_072", "ratio-tsrank-decays", "reversal",
       "(rank(ts_decay_linear(ts_corr(((high + low) / 2), adv40, 9), 10)) / rank(ts_decay_linear(ts_corr(ts_rank(vwap, 4), ts_rank(volume, 19), 7), 3)))"),
    _t("alpha_073", "max-decay-vwap-vs-mid", "reversal",
       "(max(rank(ts_decay_linear(ts_delta(vwap, 5), 3)), ts_rank(ts_decay_linear(((ts_delta(((open * 0.147155) + (low * (1 - 0.147155))), 2) / ((open * 0.147155) + (low * (1 - 0.147155)))) * -1), 3), 17)) * -1)"),
    _t("alpha_074", "rank-corr-mean-volumeprice", "reversal",
       "((rank(ts_corr(close, ts_sum(adv30, 37), 15)) < rank(ts_corr(rank(((high * 0.0261661) + (vwap * (1 - 0.0261661)))), rank(volume), 11))) * -1)"),
    _t("alpha_075", "rank-corr-volume-vs-rank-low-volume", "reversal",
       "(rank(ts_corr(vwap, volume, 4)) < rank(ts_corr(rank(low), rank(adv50), 12)))"),
    _t("alpha_076", "indneutral-decay-deltavwap", "reversal",
       "(max(rank(ts_decay_linear(ts_delta(vwap, 1), 12)), ts_rank(ts_decay_linear(ts_rank(ts_corr(group_neutralize(low, sector), adv81, 8), 20), 17), 19)) * -1)"),
    _t("alpha_077", "min-decay-rank", "reversal",
       "min(rank(ts_decay_linear((((high + low) / 2) + high) - (vwap + high), 20)), rank(ts_decay_linear(ts_corr(((high + low) / 2), adv40, 3), 6)))"),
    _t("alpha_078", "rank-corr-volume-tsrank", "reversal",
       "(rank(ts_corr(ts_sum(((low * 0.352233) + (vwap * (1 - 0.352233))), 20), ts_sum(adv40, 20), 7)) ^ rank(ts_corr(rank(vwap), rank(volume), 6)))"),
    _t("alpha_079", "indneutral-deltaclose-vs-corr", "reversal",
       "(rank(ts_delta(group_neutralize(((close * 0.60733) + (open * (1 - 0.60733))), sector), 1)) < rank(ts_corr(ts_rank(vwap, 4), ts_rank(adv150, 9), 15)))"),
    _t("alpha_080", "indneutral-deltapower-corr", "reversal",
       "((rank(sign(ts_delta(group_neutralize(((open * 0.868128) + (high * (1 - 0.868128))), industry), 4))) ^ ts_rank(ts_corr(high, adv10, 5), 6)) * -1)"),
    _t("alpha_081", "rank-corr-vwap-rank-volume", "reversal",
       "((rank(log(ts_product(rank((rank(ts_corr(vwap, ts_sum(adv10, 50), 8)) ^ 4)), 15))) < rank(ts_corr(rank(vwap), rank(volume), 5))) * -1)"),
    _t("alpha_082", "indneutral-decay-deltaopen", "reversal",
       "(min(rank(ts_decay_linear(ts_delta(open, 1), 15)), ts_rank(ts_decay_linear(ts_corr(group_neutralize(volume, sector), ((open * 0.634196) + (open * (1 - 0.634196))), 17), 7), 13)) * -1)"),
    _t("alpha_083", "rank-stddev-rangevwap", "reversal",
       "((rank(ts_delay(((high - low) / (ts_sum(close, 5) / 5)), 2)) * rank(rank(volume))) / (((high - low) / (ts_sum(close, 5) / 5)) / (vwap - close)))"),
    _t("alpha_084", "signedpower-rank-deltaclose", "reversal",
       "signed_power(ts_rank((vwap - ts_max(vwap, 15)), 21), ts_delta(close, 5))"),
    _t("alpha_085", "rank-corr-priceblend-tsrank-volumes", "reversal",
       "(rank(ts_corr(((high * 0.876703) + (close * (1 - 0.876703))), adv30, 10)) ^ rank(ts_corr(ts_rank(((high + low) / 2), 4), ts_rank(volume, 10), 7)))"),
    _t("alpha_086", "ts-rank-corr-vs-rank-pricediff", "reversal",
       "((ts_rank(ts_corr(close, ts_sum(adv20, 15), 6), 20) < rank(((open + close) - (vwap + open)))) * -1)"),
    _t("alpha_087", "indneutral-decay-vwap-blend", "reversal",
       "(max(rank(ts_decay_linear(ts_delta(((close * 0.369701) + (vwap * (1 - 0.369701))), 2), 3)), ts_rank(ts_decay_linear(abs(ts_corr(group_neutralize(adv81, industry), close, 13)), 5), 14)) * -1)"),
    _t("alpha_088", "min-decay-rank-vs-tsrank", "reversal",
       "min(rank(ts_decay_linear(((rank(open) + rank(low)) - (rank(high) + rank(close))), 8)), ts_rank(ts_decay_linear(ts_corr(ts_rank(close, 8), ts_rank(adv60, 21), 8), 7), 3))"),
    _t("alpha_089", "indneutral-tsrank-decays", "reversal",
       "(ts_rank(ts_decay_linear(ts_corr(((low * 0.967285) + (low * (1 - 0.967285))), adv10, 7), 6), 4) - ts_rank(ts_decay_linear(ts_delta(group_neutralize(vwap, industry), 3), 10), 15))"),
    _t("alpha_090", "indneutral-rank-low-vs-corr", "reversal",
       "((rank((close - ts_max(close, 5))) ^ ts_rank(ts_corr(group_neutralize(adv40, subindustry), low, 5), 3)) * -1)"),
    _t("alpha_091", "indneutral-decay-corr", "reversal",
       "((ts_rank(ts_decay_linear(ts_decay_linear(ts_corr(group_neutralize(close, industry), volume, 10), 16), 4), 5) - rank(ts_decay_linear(ts_corr(vwap, adv30, 4), 3))) * -1)"),
    _t("alpha_092", "min-tsranks-rank-decay", "reversal",
       "min(ts_rank(ts_decay_linear(((((high + low) / 2) + close) < (low + open)), 15), 19), ts_rank(ts_decay_linear(ts_corr(rank(low), rank(adv30), 8), 7), 7))"),
    _t("alpha_093", "indneutral-tsrank-decay-corr", "reversal",
       "(ts_rank(ts_decay_linear(ts_corr(group_neutralize(vwap, industry), adv81, 17), 20), 8) / rank(ts_decay_linear(ts_delta(((close * 0.524434) + (vwap * (1 - 0.524434))), 3), 16)))"),
    _t("alpha_094", "rank-vwap-tsmin", "reversal",
       "((rank((vwap - ts_min(vwap, 12))) ^ ts_rank(ts_corr(ts_rank(vwap, 20), ts_rank(adv60, 4), 18), 3)) * -1)"),
    _t("alpha_095", "rank-vs-tsrank-corr", "reversal",
       "(rank((open - ts_min(open, 12))) < ts_rank((rank(ts_corr(ts_sum(((high + low) / 2), 19), ts_sum(adv40, 19), 13)) ^ 5), 12))"),
    _t("alpha_096", "max-tsrank-decay-corr", "reversal",
       "(max(ts_rank(ts_decay_linear(ts_corr(rank(vwap), rank(volume), 4), 4), 8), ts_rank(ts_decay_linear(ts_arg_max(ts_corr(ts_rank(close, 7), ts_rank(adv60, 4), 4), 13), 14), 13)) * -1)"),
    _t("alpha_097", "indneutral-decay-deltablend", "reversal",
       "((rank(ts_decay_linear(ts_delta(group_neutralize(((low * 0.721001) + (vwap * (1 - 0.721001))), industry), 3), 20)) - ts_rank(ts_decay_linear(ts_rank(ts_corr(ts_rank(low, 8), ts_rank(adv60, 17), 5), 19), 16), 7)) * -1)"),
    _t("alpha_098", "rank-decay-corr-vs-rank-decay-tsrank", "reversal",
       "(rank(ts_decay_linear(ts_corr(vwap, ts_sum(adv5, 26), 5), 7)) - rank(ts_decay_linear(ts_rank(ts_arg_min(ts_corr(rank(open), rank(adv15), 21), 9), 7), 8)))"),
    _t("alpha_099", "rank-corr-volume-low-vs-volume", "reversal",
       "((rank(ts_corr(ts_sum(((high + low) / 2), 20), ts_sum(adv60, 20), 9)) < rank(ts_corr(low, volume, 6))) * -1)"),
    _t("alpha_100", "indneutral-rank-and-corr-volumeproxy", "reversal",
       "(0 - (1 * (((1.5 * scale(group_neutralize(group_neutralize(rank(((((close - low) - (high - close)) / (high - low)) * volume)), subindustry), subindustry))) - scale(group_neutralize((ts_corr(close, rank(adv20), 5) - rank(ts_arg_min(close, 30))), subindustry))) * (volume / adv20))))"),
    _t("alpha_101", "close-open-over-range", "reversal",
       "((close - open) / ((high - low) + 0.001))"),
]


# ---------------------------------------------------------------------------
# Classical equity factors (non-Alpha101) - well-known starting points
# ---------------------------------------------------------------------------
_CLASSICAL_SRC = "Classical academic factors"

CLASSICAL_FACTORS: List[Dict] = [
    _t("mom_12_1", "12-1 Month Price Momentum", "momentum",
       "(ts_delay(close, 21) / ts_delay(close, 252)) - 1",
       "Jegadeesh & Titman 1993"),
    _t("mom_6_1", "6-1 Month Price Momentum", "momentum",
       "(ts_delay(close, 21) / ts_delay(close, 126)) - 1",
       "Jegadeesh & Titman 1993"),
    _t("mom_12_1_volscaled", "Risk-Adjusted Momentum", "momentum",
       "((ts_delay(close, 21) / ts_delay(close, 252)) - 1) / ts_std_dev(returns, 252)",
       "Frazzini-Pedersen style"),

    _t("rev_1m", "1-Month Short-Term Reversal", "reversal",
       "-1 * ts_sum(returns, 21)",
       "Jegadeesh 1990"),
    _t("rev_1w", "1-Week Short-Term Reversal", "reversal",
       "-1 * ts_sum(returns, 5)",
       "De Bondt & Thaler 1985"),
    _t("rev_overnight", "Overnight Reversal", "reversal",
       "-1 * ts_sum(((open - ts_delay(close, 1)) / ts_delay(close, 1)), 5)",
       "Lou et al. 2018"),

    _t("vol_low_1m", "Low Volatility (1m)", "low_vol",
       "-1 * ts_std_dev(returns, 21)",
       "Ang, Hodrick, Xing & Zhang 2006"),
    _t("vol_low_3m", "Low Volatility (3m)", "low_vol",
       "-1 * ts_std_dev(returns, 63)",
       "Ang, Hodrick, Xing & Zhang 2006"),
    _t("idiosyncratic_vol", "Idiosyncratic Volatility (residual)", "low_vol",
       "-1 * ts_std_dev(regression_neut(returns, ts_mean(returns, 21)), 63)",
       "Ang, Hodrick, Xing & Zhang 2006"),

    _t("liquidity_amihud", "Amihud Illiquidity (signed -)", "liquidity",
       "-1 * ts_mean(abs(returns) / (close * volume + 1), 21)",
       "Amihud 2002"),
    _t("liquidity_turnover", "Turnover (signed -)", "liquidity",
       "-1 * ts_mean(volume / sharesout, 21)",
       "Datar, Naik & Radcliffe 1998"),

    _t("beta_60", "60d Beta to market mean (negative)", "low_vol",
       "-1 * ts_regression(returns, ts_mean(returns, 1), 60, 0, 0)",
       "Frazzini-Pedersen Betting Against Beta"),

    _t("size_smb", "Size (small minus big)", "size",
       "-1 * log(cap)",
       "Fama-French 1992"),

    _t("trend_50_200", "Trend: SMA50 above SMA200", "momentum",
       "(ts_mean(close, 50) / ts_mean(close, 200)) - 1",
       "Faber 2006"),

    _t("hh_ratio", "High-Low range vs close", "volatility",
       "(ts_max(high, 20) - ts_min(low, 20)) / close",
       "Parkinson 1980"),
    _t("garman_klass_vol", "Garman-Klass Volatility (signed -)", "low_vol",
       "-1 * ts_mean(0.5 * (log(high / low)) * (log(high / low)) - (2 * log(2) - 1) * (log(close / open)) * (log(close / open)), 20)",
       "Garman & Klass 1980"),

    _t("vwap_dev", "Deviation from VWAP", "reversal",
       "(close - vwap) / vwap"),
    _t("close_to_high", "Close strength within bar", "reversal",
       "(close - low) / (high - low + 0.0001)"),
    _t("range_position", "Range position over 20d", "reversal",
       "(close - ts_min(low, 20)) / (ts_max(high, 20) - ts_min(low, 20) + 0.0001)"),

    _t("volume_shock", "Volume Shock", "liquidity",
       "rank(ts_zscore(volume, 20))"),
    _t("dollar_volume_shock", "Dollar Volume Shock", "liquidity",
       "rank(ts_zscore(close * volume, 20))"),

    _t("return_skew_60", "Return Skewness (negative)", "skewness",
       "-1 * ts_skewness(returns, 60)",
       "Bali, Engle & Murray 2016"),
    _t("return_kurt_60", "Return Kurtosis (negative)", "kurtosis",
       "-1 * ts_kurtosis(returns, 60)"),

    _t("sector_neut_mom", "Sector-neutral 12-1 momentum", "momentum",
       "group_neutralize((ts_delay(close, 21) / ts_delay(close, 252)) - 1, sector)"),
    _t("sector_neut_rev", "Sector-neutral 1m reversal", "reversal",
       "group_neutralize(-1 * ts_sum(returns, 21), sector)"),
    _t("industry_neut_lowvol", "Industry-neutral low vol", "low_vol",
       "group_neutralize(-1 * ts_std_dev(returns, 63), industry)"),
]


ALL_TEMPLATES: List[Dict] = ALPHA_101 + CLASSICAL_FACTORS


def templates_by_category() -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for t in ALL_TEMPLATES:
        out.setdefault(t["category"], []).append(t)
    return out
