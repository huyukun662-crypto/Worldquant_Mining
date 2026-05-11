"""OpenAlpha factor catalog translated to WorldQuant Brain FASTEXPR.

Source: https://github.com/ziyouqitan/OpenAlpha (src/ruiqiwang_csi_500.txt).

The upstream factors target the Chinese A-share CSI-500 universe with a
domain-specific DSL. This module ports them to WQ Brain FASTEXPR over
the USA TOP3000 universe.

Translation conventions:

  OpenAlpha               -> WQ Brain FASTEXPR
  ts_correlation(x,y,d)   -> ts_corr(x, y, d)
  ts_std(x, d)            -> ts_std_dev(x, d)
  np.abs(x)               -> abs(x)
  cs_rank(x)              -> rank(x)
  ts_ret(x, 1)            -> ts_returns(x, 1)
  ret1                    -> returns                  (WQ 1d return field)
  csi_500_ret1            -> group_mean(returns,1,market)
  amount                  -> vwap * volume
  ts_ols(y,x,d)[0]        -> ts_regression(y,x,d,rettype=2)  (beta/slope)
  ts_ols(y,x,d)[2]        -> ts_regression(y,x,d,rettype=0)  (residual)
  cs_indneut(x, ...)      -> x                          (handled by settings)
  cs_booksize(x)          -> x                          (handled by settings)
  at_mask(x, csi_weight)  -> x                          (US universe is set
                                                          via settings)
  ts_fill(x)              -> x

Two factors are skipped:
- Original #33 depends on csi_500_open/csi_500_close which have no
  clean USA market analogue.
- N/A.

Each entry: (id, name, original, translated).
"""

from __future__ import annotations

FACTORS: list[tuple[str, str, str, str]] = [
    (
        "OA01",
        "vwap_close_mean5",
        "ts_mean(vwap-close,5)",
        "ts_mean(vwap - close, 5)",
    ),
    (
        "OA02",
        "neg_corr_close_volume_5",
        "-ts_correlation(close, volume, 5)",
        "-1 * ts_corr(close, volume, 5)",
    ),
    (
        "OA03",
        "rank_open_minus_rank_delay_close",
        "cs_rank(cs_rank(open)-cs_rank(ts_delay(close,1)))",
        "rank(rank(open) - rank(ts_delay(close, 1)))",
    ),
    (
        "OA04",
        "corr_lowret_ret_3",
        "ts_correlation(ts_ret(low,1),ret1,3)",
        "ts_corr(ts_returns(low, 1), returns, 3)",
    ),
    (
        "OA05",
        "ols_residual_openClose_volume_10",
        "ts_ols(open/ts_delay(close,1),ts_delay(volume,1),10)[2]",
        "ts_regression(open/ts_delay(close, 1), ts_delay(volume, 1), 10, rettype=0)",
    ),
    (
        "OA06",
        "neg_ols_residual_close_ret_10",
        "-ts_ols(close,ret1,10)[2]",
        "-1 * ts_regression(close, returns, 10, rettype=0)",
    ),
    (
        "OA07",
        "neg_corr_close_closeLowMinus1_15",
        "-ts_correlation(close,close/low-1,15)",
        "-1 * ts_corr(close, close/low - 1, 15)",
    ),
    (
        "OA08",
        "neg_corr_close_abs_ret_5",
        "-ts_correlation(close,np.abs(ret1),5)",
        "-1 * ts_corr(close, abs(returns), 5)",
    ),
    (
        "OA09",
        "neg_corr_close_closeVwapMinus1_20",
        "-ts_correlation(close,close/vwap-1,20)",
        "-1 * ts_corr(close, close/vwap - 1, 20)",
    ),
    (
        "OA10",
        "corr_rankDelayVolume_rankRet_5",
        "ts_correlation(cs_rank(ts_delay(volume,1)),cs_rank(ret1),5)",
        "ts_corr(rank(ts_delay(volume, 1)), rank(returns), 5)",
    ),
    (
        "OA11",
        "neg_priceVolume_zscoreRet",
        "-close*volume*ts_zscore(ret1,2)",
        "-1 * close * volume * ts_zscore(returns, 2)",
    ),
    (
        "OA12",
        "corr_ret_marketRet_20",
        "ts_correlation(ret1,csi_500_ret1,20)",
        "ts_corr(returns, group_mean(returns, 1, market), 20)",
    ),
    (
        "OA13",
        "ols_beta_ret_delayMarketRet_5",
        "ts_ols(ret1,ts_delay(csi_500_ret1,1),5)[0]",
        "ts_regression(returns, ts_delay(group_mean(returns, 1, market), 1), 5, rettype=2)",
    ),
    (
        "OA14",
        "ols_beta_ret_delayRet_20",
        "ts_ols(ret1,ts_delay(ret1,1),20)[0]",
        "ts_regression(returns, ts_delay(returns, 1), 20, rettype=2)",
    ),
    (
        "OA15",
        "neg_ols_residual_ret_delayRet_20",
        "-ts_ols(ret1,ts_delay(ret1,1),20)[2]",
        "-1 * ts_regression(returns, ts_delay(returns, 1), 20, rettype=0)",
    ),
    (
        "OA16",
        "neg_ols_beta_ret_volume_10",
        "-ts_ols(ret1,volume,10)[0]",
        "-1 * ts_regression(returns, volume, 10, rettype=2)",
    ),
    (
        "OA17",
        "neg_ols_residual_rankHigh_rankLow_10",
        "-ts_ols(cs_rank(high),cs_rank(low),10)[2]",
        "-1 * ts_regression(rank(high), rank(low), 10, rettype=0)",
    ),
    (
        "OA18",
        "neg_ols_residual_rankHigh_rankOpen_20",
        "-ts_ols(cs_rank(high),cs_rank(open),20)[2]",
        "-1 * ts_regression(rank(high), rank(open), 20, rettype=0)",
    ),
    (
        "OA19",
        "high_minus_close_indneut",
        "cs_indneut(high-close, cs_group_quantile(at_mask(close,...),10))",
        "high - close",
    ),
    (
        "OA20",
        "vwap_minus_close_mean2",
        "ts_mean(at_mask(vwap-close, cs_rank(...) > 0.5), 2)",
        "ts_mean(vwap - close, 2)",
    ),
    (
        "OA21",
        "neg_skew_close_20",
        "-ts_skewness(close,20)",
        "-1 * ts_skewness(close, 20)",
    ),
    (
        "OA22",
        "skew_vwap_minus_close_10",
        "ts_skewness(vwap-close,10)",
        "ts_skewness(vwap - close, 10)",
    ),
    (
        "OA23",
        "kurt_delta_close_20",
        "ts_kurtosis(ts_delta(close,1),20)",
        "ts_kurtosis(ts_delta(close, 1), 20)",
    ),
    (
        "OA24",
        "vol_low_minus_vol_high_100",
        "ts_std(low/ts_delay(close,1)-1,100) - ts_std(high/ts_delay(close,1)-1,100)",
        "ts_std_dev(low/ts_delay(close, 1) - 1, 100) - ts_std_dev(high/ts_delay(close, 1) - 1, 100)",
    ),
    (
        "OA25",
        "mean_open_minus_close_2_indneut",
        "cs_indneut(ts_mean(open-close,2), ...)",
        "ts_mean(open - close, 2)",
    ),
    (
        "OA26",
        "ols_beta_marketRet_ret_5",
        "ts_ols(csi_500_ret1,ret1,5)[0]",
        "ts_regression(group_mean(returns, 1, market), returns, 5, rettype=2)",
    ),
    (
        "OA27",
        "neg_regression_marketRet_delayRet_50",
        "-ts_regression(csi_500_ret1,ts_delay(ret1,1),50,0)",
        "-1 * ts_regression(group_mean(returns, 1, market), ts_delay(returns, 1), 50, rettype=0)",
    ),
    (
        "OA28",
        "neg_regression_marketRet_amount_30",
        "-ts_regression(csi_500_ret1,amount,30,0)",
        "-1 * ts_regression(group_mean(returns, 1, market), vwap * volume, 30, rettype=0)",
    ),
    (
        "OA29",
        "neg_ols_beta_excessRet_ret_5",
        "-ts_ols(ret1-csi_500_ret1,ret1,5)[0]",
        "-1 * ts_regression(returns - group_mean(returns, 1, market), returns, 5, rettype=2)",
    ),
    (
        "OA30",
        "neg_ols_beta_tsRankClose_tsRankAbsRet_10",
        "-ts_ols(ts_rank(close,10),ts_rank(np.abs(ret1),10),10)[0]",
        "-1 * ts_regression(ts_rank(close, 10), ts_rank(abs(returns), 10), 10, rettype=2)",
    ),
    (
        "OA31",
        "neg_ols_residual_tsRankClose_tsRankVwap_3",
        "-ts_ols(ts_rank(close,3),ts_rank(vwap,3),3)[2]",
        "-1 * ts_regression(ts_rank(close, 3), ts_rank(vwap, 3), 3, rettype=0)",
    ),
    (
        "OA32",
        "neg_regression_tsRankClose_tsRankRet_10",
        "-ts_regression(ts_rank(close,10),ts_rank(ret1,10),10,5)",
        "-1 * ts_regression(ts_rank(close, 10), ts_rank(returns, 10), 10, rettype=0)",
    ),
    (
        "OA34",
        "ols_beta_skewRet_ret_5",
        "ts_ols(ts_skewness(ret1,5),ret1,5)[0]",
        "ts_regression(ts_skewness(returns, 5), returns, 5, rettype=2)",
    ),
    (
        "OA35",
        "neg_regression_skewRet_ret_7",
        "-ts_regression(ts_skewness(ret1,3),ret1,7,9)",
        "-1 * ts_regression(ts_skewness(returns, 3), returns, 7, rettype=0)",
    ),
]


def all_expressions() -> list[dict]:
    return [
        {
            "id": fid,
            "name": name,
            "original": original,
            "expression": translated,
        }
        for (fid, name, original, translated) in FACTORS
    ]


if __name__ == "__main__":
    import json
    print(json.dumps(all_expressions(), indent=2))
