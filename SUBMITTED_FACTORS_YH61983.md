# Submitted factors — account 2445560398@qq.com (user YH61983)

Total submitted: **40**  (D1: 27, D0: 13)


## `gJ3Qvvzm`  D1  SPECTACULAR
- IS: Sharpe **2.76** · fitness 3.51 · turnover 0.1118 · returns 0.2016 · drawdown 0.0399 · margin 0.003607 · selfCorr 0.6773
- Settings: `region=USA  universe=TOP3000  delay=1  decay=15  neutralization=SUBINDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
reverse(zscore(ts_decay_linear(add(add(zscore(divide(ts_backfill(implied_volatility_put_30, 5), ts_backfill(implied_volatility_call_30, 5))), zscore(divide(ts_backfill(implied_volatility_put_60, 5), ts_backfill(implied_volatility_call_60, 5)))), zscore(divide(ts_backfill(implied_volatility_put_90, 5), ts_backfill(implied_volatility_call_90, 5)))), 15)))
```

## `RRN516od`  D1  GOOD
- IS: Sharpe **2.7** · fitness 1.9 · turnover 0.2619 · returns 0.1292 · drawdown 0.043 · margin 0.000987 · selfCorr 0.761
- Settings: `region=USA  universe=TOP3000  delay=1  decay=8  neutralization=INDUSTRY  truncation=0.05  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```

rank(
  (rank((rank((rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_chg12msip, 120), 20)))
              + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_fangma_rvm_usa_fangma_rvm6, 120), 20))))))) 
        + (-1 * (rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))))))
  + (rank(divide(subtract(vwap, close), close)))
)
```

## `2rvOwEqw`  D1  EXCELLENT  ⭐ **D1 #2**
- IS: Sharpe **2.38** · fitness 2.45 · turnover 0.048 · returns 0.1323 · drawdown 0.0599 · margin 0.005517 · selfCorr 0.581
- Settings: `region=USA  universe=TOP3000  delay=1  decay=6  neutralization=SUBINDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
g = ts_backfill(mdl177_2_garpanalystmodel_qgp_composite, 30);
iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);
score = quantile(iv) + 0.5 * quantile(g);
gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.80);
trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)
```

## `WjNe3zmj`  D1  SPECTACULAR  ⭐ **D1 #1**
- IS: Sharpe **2.28** · fitness 2.67 · turnover 0.0541 · returns 0.1716 · drawdown 0.111 · margin 0.006343 · selfCorr 0.6249
- Settings: `region=USA  universe=TOP3000  delay=1  decay=4  neutralization=SUBINDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
curv = ts_backfill(pcr_oi_30 + pcr_oi_180 - 2 * pcr_oi_90, 5);
iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);
supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);
tightness = -ts_zscore(supply, 120);
score = quantile(iv) + 0.5 * quantile(tightness) + 0.3 * quantile(curv);
gate = (ts_backfill(news_pct_90min, 5) < 1) * (ts_rank(abs(news_pct_30min), 60) > 0.80);
trade_when(gate, ts_decay_linear(signed_power(score - 0.5, 3), 5), -1)
```

## `VkXjKN7b`  D1  SPECTACULAR
- IS: Sharpe **2.19** · fitness 3.45 · turnover 0.1765 · returns 0.4371 · drawdown 0.3172 · margin 0.004952 · selfCorr 0.6379
- Settings: `region=USA  universe=TOP3000  delay=1  decay=8  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 2)), log(add(divide(volume, adv20), 1))), 30)))
```

## `QPnW5LWQ`  D1  GOOD
- IS: Sharpe **2.17** · fitness 1.87 · turnover 0.1329 · returns 0.0984 · drawdown 0.054 · margin 0.00148 · selfCorr 0.5203
- Settings: `region=USA  universe=TOP3000  delay=1  decay=8  neutralization=INDUSTRY  truncation=0.05  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
rank(
  (rank((rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_chg12msip, 120), 20)))
        + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_fangma_rvm_usa_fangma_rvm6, 120), 20)))))))
  + (-1 * (rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))))
)
```

## `1YgAgalW`  D1  AVERAGE
- IS: Sharpe **2.02** · fitness 1.38 · turnover 0.0173 · returns 0.0584 · drawdown 0.0257 · margin 0.00675 · selfCorr 0.6895
- Settings: `region=USA  universe=TOP3000  delay=1  decay=6  neutralization=INDUSTRY  truncation=2e-05  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
zscore(ts_decay_linear(signed_power(add(add(group_neutralize(zscore(divide(ts_backfill(fnd6_drc, 45), ts_backfill(assets, 45))), subindustry), group_neutralize(zscore(divide(ts_backfill(fnd6_drlt, 45), ts_backfill(assets, 45))), subindustry)), multiply(0.4, add(group_neutralize(reverse(zscore(ts_backfill(earnings_certainty_rank_derivative, 10))), subindustry), group_neutralize(reverse(zscore(ts_backfill(analyst_revision_rank_derivative, 10))), subindustry)))), 1.17), 10))
```

## `blNEelXq`  D1  GOOD
- IS: Sharpe **2.0** · fitness 1.65 · turnover 0.1998 · returns 0.1363 · drawdown 0.0847 · margin 0.001364 · selfCorr 0.6703
- Settings: `region=USA  universe=TOP3000  delay=1  decay=6  neutralization=INDUSTRY  truncation=0.1  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
add (add (add (group_rank(ts_mean(divide (ebit, cap), 120), subindustry), -group_rank(ts_sum(returns, 3), subindustry)), group_rank(ts_zscore(adv20, 60),subindustry)), group_rank(ts_mean(divide(implied_volatility_call_270,implied_volatility_put_270), 22), sector))
```

## `88Od9aml`  D1  EXCELLENT
- IS: Sharpe **1.91** · fitness 2.03 · turnover 0.0706 · returns 0.1416 · drawdown 0.1192 · margin 0.004008 · selfCorr 0.5858
- Settings: `region=USA  universe=TOP3000  delay=1  decay=0  neutralization=SUBINDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
skew = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 20);
gate = (ts_backfill(news_pct_120min, 20) < 2) *
       (ts_rank(abs(news_pct_30min), 130) > 0.85);
trade_when(gate, skew, -1)
```

## `kqnapLqz`  D1  AVERAGE
- IS: Sharpe **1.8** · fitness 1.07 · turnover 0.1616 · returns 0.0566 · drawdown 0.0293 · margin 0.000701 · selfCorr 0.2867
- Settings: `region=USA  universe=TOP3000  delay=1  decay=8  neutralization=INDUSTRY  truncation=0.05  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
rank((rank(ts_av_diff(ts_backfill(mdl177_2_sensitivityfactor400_chg12msip, 120), 20))) + ((-1 * (rank(ts_av_diff(ts_backfill(mdl177_fangma_rvm_usa_fangma_rvm6, 120), 20))))))
```

## `1YgO3R6k`  D1  GOOD
- IS: Sharpe **1.71** · fitness 1.55 · turnover 0.0192 · returns 0.1022 · drawdown 0.0485 · margin 0.010653 · selfCorr 0.8036
- Settings: `region=USA  universe=TOP3000  delay=1  decay=10  neutralization=INDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
zscore(ts_decay_linear(add(add(add(add(add(group_neutralize(zscore(divide(ts_backfill(debt, 60), ts_backfill(equity, 60))), subindustry), group_neutralize(zscore(divide(ts_backfill(debt, 60), ts_backfill(assets, 60))), subindustry)), group_neutralize(zscore(divide(ts_backfill(debt_lt, 60), ts_backfill(assets, 60))), subindustry)), group_neutralize(zscore(divide(ts_backfill(debt_lt, 60), ts_backfill(equity, 60))), subindustry)), multiply(0.5, add(group_neutralize(zscore(divide(ts_backfill(fnd6_mfma2_revt, 60), ts_backfill(assets, 60))), subindustry), group_neutralize(zscore(divide(ts_backfill(fnd6_mfma2_revt, 60), ts_backfill(equity, 60))), subindustry)))), multiply(0.2, group_neutralize(reverse(zscore(ts_backfill(earnings_certainty_rank_derivative, 10))), subindustry))), 15))
```

## `QPnJnLjg`  D1  GOOD
- IS: Sharpe **1.7** · fitness 1.51 · turnover 0.1347 · returns 0.1062 · drawdown 0.1068 · margin 0.001578 · selfCorr 0.4234
- Settings: `region=USA  universe=TOP3000  delay=1  decay=8  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 3), log(add(divide(volume, adv20), 1))), 50)))
```

## `xAeKeo7l`  D1  AVERAGE
- IS: Sharpe **1.7** · fitness 1.34 · turnover 0.2131 · returns 0.1324 · drawdown 0.0606 · margin 0.001242 · selfCorr 0.9518
- Settings: `region=USA  universe=TOP3000  delay=1  decay=0  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
group_neutralize(ts_decay_linear(if_else(ts_rank(returns, 252) > 0.85, -1, if_else(ts_rank(returns, 252) < 0.15, 1, 0)), 60), subindustry)
```

## `1Y7mXbX6`  D1  AVERAGE
- IS: Sharpe **1.69** · fitness 1.31 · turnover 0.0714 · returns 0.0754 · drawdown 0.0378 · margin 0.002113 · selfCorr 0.4928
- Settings: `region=USA  universe=TOP1000  delay=1  decay=5  neutralization=SUBINDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
	rank(ts_zscore(equity/cap,250)) + rank(ts_mean(ts_delta(anl4_afv4_eps_mean,20),60))
```

## `9q9qJ0KK`  D1  AVERAGE
- IS: Sharpe **1.68** · fitness 1.11 · turnover 0.2532 · returns 0.11 · drawdown 0.0692 · margin 0.000869 · selfCorr 0.5948
- Settings: `region=USA  universe=TOP3000  delay=1  decay=0  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
group_neutralize(ts_decay_linear(0.9 * rank(ts_corr(returns, ts_mean(returns, 1), 60)) + 0.1 * -ts_rank(close - vwap, 252), 60), industry)
```

## `kq3d0qAd`  D1  AVERAGE
- IS: Sharpe **1.57** · fitness 1.34 · turnover 0.106 · returns 0.0905 · drawdown 0.0676 · margin 0.001707 · selfCorr 0.7536
- Settings: `region=USA  universe=TOP1000  delay=1  decay=4  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
trade_when(abs(close/ts_mean(close,15)-1) > 0.08, -ts_rank(close/ts_mean(close,15),7), -1)
```

## `58LMQOnJ`  D1  GOOD
- IS: Sharpe **1.57** · fitness 1.84 · turnover 0.0447 · returns 0.1724 · drawdown 0.1517 · margin 0.00771 · selfCorr 0.4587
- Settings: `region=USA  universe=TOP3000  delay=1  decay=0  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq,100)/ ts_mean   (mdl77_liquidityriskfactor_milliq,100)* ts_std_dev(mdl77_liquidityriskfactor_cvvolp20d, 100) / ts_mean   (mdl77_liquidityriskfactor_cvvolp20d, 100)
```

## `P0pwmwqq`  D1  AVERAGE
- IS: Sharpe **1.54** · fitness 1.24 · turnover 0.129 · returns 0.0837 · drawdown 0.0485 · margin 0.001297 · selfCorr 0.3165
- Settings: `region=USA  universe=TOP1000  delay=1  decay=18  neutralization=SUBINDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
rank(add(add(add(add(add(
  rank(-ts_corr(close, volume, 20)),                                   # 量价背离
  -rank(ts_rank(returns, 60))),                                        # 60日排序 
  -rank(ts_mean(divide(abs(returns), multiply(close, volume)), 60))),  # Amihud
  rank(ts_mean(divide(volume, sharesout), 60))),                       # 换手率
  rank(ts_zscore(volume, 60))),                                        # 异常成交 
  rank(ts_mean(divide(open, ts_delay(close, 1)), 20))))               # 隔夜跳空 
```

## `pw61Z6xx`  D1  AVERAGE
- IS: Sharpe **1.53** · fitness 1.25 · turnover 0.0651 · returns 0.0833 · drawdown 0.0739 · margin 0.002558 · selfCorr 0.576
- Settings: `region=USA  universe=TOP1000  delay=1  decay=5  neutralization=SUBINDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
	rank(ts_zscore(ebit/cap,250)) + rank(ts_mean(ts_delta(anl4_afv4_eps_mean,20),60))
```

## `QPQAWN9g`  D1  AVERAGE
- IS: Sharpe **1.53** · fitness 1.17 · turnover 0.0161 · returns 0.0736 · drawdown 0.0474 · margin 0.009128 · selfCorr 0.5711
- Settings: `region=USA  universe=TOP3000  delay=1  decay=128  neutralization=SUBINDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
rank(divide(liabilities_curr, assets))
```

## `6Xakb2n5`  D1  AVERAGE
- IS: Sharpe **1.53** · fitness 1.16 · turnover 0.2372 · returns 0.1374 · drawdown 0.1076 · margin 0.001159 · selfCorr 0.7279
- Settings: `region=USA  universe=TOP3000  delay=1  decay=0  neutralization=SECTOR  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
group_neutralize(ts_decay_linear(-ts_rank(returns, 144), 60), subindustry)
```

## `d5xmG6LX`  D1  AVERAGE
- IS: Sharpe **1.5** · fitness 1.02 · turnover 0.1702 · returns 0.0785 · drawdown 0.0772 · margin 0.000922 · selfCorr 0.53
- Settings: `region=USA  universe=TOP1000  delay=1  decay=5  neutralization=SUBINDUSTRY  truncation=0.01  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
rank(ts_rank(cashflow_op/cap, 40)) + rank(ts_rank(ebit/equity, 40))
```

## `le013Rze`  D1  AVERAGE
- IS: Sharpe **1.46** · fitness 1.12 · turnover 0.0138 · returns 0.0737 · drawdown 0.078 · margin 0.010645 · selfCorr 0.3292
- Settings: `region=USA  universe=TOP3000  delay=1  decay=6  neutralization=INDUSTRY  truncation=0.005  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
zscore(ts_decay_linear(add(group_neutralize(zscore(divide(ts_backfill(fnd6_drc, 90), ts_backfill(assets, 90))), subindustry), group_neutralize(zscore(divide(ts_backfill(fnd6_drlt, 90), ts_backfill(assets, 90))), subindustry)), 10))
```

## `omK1bVKk`  D1  AVERAGE
- IS: Sharpe **1.39** · fitness 1.02 · turnover 0.0825 · returns 0.0667 · drawdown 0.059 · margin 0.001617 · selfCorr 0.6739
- Settings: `region=USA  universe=TOP3000  delay=1  decay=4  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
trade_when(abs(close/ts_mean(close,20)-1) > 0.12, -ts_rank(close/ts_mean(close,20),7), -1)
```

## `58LxoMxJ`  D1  AVERAGE
- IS: Sharpe **1.36** · fitness 1.12 · turnover 0.2271 · returns 0.1529 · drawdown 0.1318 · margin 0.001346 · selfCorr 0.4847
- Settings: `region=USA  universe=TOP200  delay=1  decay=0  neutralization=INDUSTRY  truncation=0.05  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
group_neutralize(ts_decay_linear(-ts_rank(returns - ts_mean(returns, 60), 504), 60), subindustry)
```

## `omYLkld6`  D1  AVERAGE
- IS: Sharpe **1.35** · fitness 1.43 · turnover 0.024 · returns 0.1411 · drawdown 0.1087 · margin 0.011741 · selfCorr 0.442
- Settings: `region=USA  universe=TOP3000  delay=1  decay=6  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
zscore(ts_decay_linear(add(add(group_neutralize(reverse(zscore(divide(ts_backfill(cashflow, 60), ts_backfill(assets, 60)))), subindustry), group_neutralize(reverse(zscore(divide(ts_backfill(cashflow, 60), ts_backfill(fnd6_mfma2_revt, 60)))), subindustry)), multiply(0.5, group_neutralize(reverse(zscore(divide(ts_backfill(cashflow, 60), ts_backfill(ebitda, 60)))), subindustry))), 10))
```

## `A13xezNX`  D1  AVERAGE
- IS: Sharpe **1.29** · fitness 1.16 · turnover 0.0288 · returns 0.1008 · drawdown 0.0909 · margin 0.007003 · selfCorr 0.431
- Settings: `region=USA  universe=TOP3000  delay=1  decay=6  neutralization=INDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
zscore(ts_decay_linear(add(add(multiply(0.7, add(add(group_neutralize(reverse(zscore(divide(ts_backfill(cashflow, 60), ts_backfill(assets, 60)))), subindustry), group_neutralize(reverse(zscore(divide(ts_backfill(cashflow, 60), ts_backfill(fnd6_mfma2_revt, 60)))), subindustry)), multiply(0.5, group_neutralize(reverse(zscore(divide(ts_backfill(cashflow, 60), ts_backfill(ebitda, 60)))), subindustry)))), add(add(group_neutralize(reverse(zscore(divide(ts_backfill(pretax_income, 60), ts_backfill(assets, 60)))), subindustry), group_neutralize(reverse(zscore(divide(ts_backfill(pretax_income, 60), ts_backfill(fnd6_mfma2_revt, 60)))), subindustry)), multiply(0.5, group_neutralize(reverse(zscore(divide(ts_backfill(pretax_income, 60), ts_backfill(equity, 60)))), subindustry)))), add(group_neutralize(zscore(divide(ts_backfill(fnd6_mfma2_revt, 60), ts_backfill(assets, 60))), subindustry), group_neutralize(zscore(divide(ts_backfill(fnd6_mfma2_revt, 60), ts_backfill(equity, 60))), subindustry))), 10))
```

## `0mz3J1AG`  D0  EXCELLENT
- IS: Sharpe **2.73** · fitness 3.02 · turnover 0.0715 · returns 0.1532 · drawdown 0.0395 · margin 0.004283 · selfCorr 0.9183
- Settings: `region=USA  universe=TOP3000  delay=0  decay=4  neutralization=INDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
winsorize(ts_decay_linear(group_zscore(ts_mean(((implied_volatility_call_30 - implied_volatility_put_30) / ts_std_dev(returns, 30)), 40), sector), 4), std=4)
```

## `GrkeWwx5`  D0  AVERAGE
- IS: Sharpe **2.22** · fitness 1.56 · turnover 0.1909 · returns 0.0946 · drawdown 0.0359 · margin 0.000991 · selfCorr 0.5262
- Settings: `region=USA  universe=TOP3000  delay=0  decay=4  neutralization=SUBINDUSTRY  truncation=0.05  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
add(add(add(multiply(if_else(is_nan(group_zscore(ts_mean(ts_backfill(news_short_interest, 22), 22), subindustry)), group_zscore(ts_mean(ts_backfill(news_pct_90min, 5), 10), subindustry), multiply(group_zscore(ts_mean(ts_backfill(news_short_interest, 22), 22), subindustry), 3)), 3), multiply(group_zscore(ts_mean(ts_backfill(news_pct_90min, 5), 10), subindustry), 1)), multiply(group_zscore(ts_backfill(divide(est_epsr, close), 120), subindustry), 1)), multiply(group_zscore(ts_delta(close, 5), subindustry), -0.7))
```

## `mLZkOw6x`  D0  GOOD
- IS: Sharpe **2.21** · fitness 2.18 · turnover 0.0704 · returns 0.1211 · drawdown 0.0404 · margin 0.003442 · selfCorr 0.655
- Settings: `region=USA  universe=TOP3000  delay=0  decay=4  neutralization=INDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
winsorize(ts_decay_linear(group_zscore(ts_mean(((implied_volatility_call_30 - implied_volatility_put_30) / parkinson_volatility_30), 40), sector), 4), std=4)
```

## `d5QK2b3E`  D0  AVERAGE
- IS: Sharpe **2.18** · fitness 1.78 · turnover 0.2217 · returns 0.148 · drawdown 0.07 · margin 0.001335 · selfCorr 0.733
- Settings: `region=USA  universe=TOP3000  delay=0  decay=4  neutralization=NONE  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
subtract(add(add(add(add(multiply(1.5,group_zscore(quantile(divide(ts_mean(volume, 5), ts_mean(volume, 60)), driver=gaussian), subindustry)), multiply(1.5,group_zscore(quantile(multiply(-1, ts_mean(divide(abs(returns), multiply(vwap, volume)), 22)), driver=gaussian), subindustry))), multiply(1.5,group_zscore(quantile(ts_backfill(divide(est_bookvalue_ps, close), 22), driver=gaussian), subindustry))), multiply(1.5,group_zscore(quantile(ts_backfill(divide(est_grossincome, est_tot_assets), 22), driver=gaussian), subindustry))), multiply(1.5,group_zscore(quantile(ts_backfill(divide(sales, est_tot_assets), 22), driver=gaussian), subindustry))), add(group_zscore(quantile(ts_av_diff(close, 5), driver=gaussian), subindustry), group_zscore(quantile(ts_corr(close, volume, 5), driver=gaussian), subindustry)))
```

## `akN9pwQw`  D0  GOOD  ⭐ **D0 #1**
- IS: Sharpe **2.14** · fitness 2.16 · turnover 0.0949 · returns 0.1273 · drawdown 0.0729 · margin 0.002684 · selfCorr 0.6855
- Settings: `region=USA  universe=TOP3000  delay=0  decay=12  neutralization=INDUSTRY  truncation=0.05  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
winsorize(trade_when((ts_rank(abs(news_pct_30min), 60) > 0.120), ts_decay_linear(1.800 * group_zscore((implied_volatility_call_20 - implied_volatility_put_20), sector) + 0.900 * group_zscore(snt_value, sector) + 0.400 * group_zscore((-1 * ts_zscore(returns, 10)), sector), 30), -1), std=4)
```

## `1YgRP5vX`  D0  AVERAGE
- IS: Sharpe **2.12** · fitness 1.8 · turnover 0.149 · returns 0.1078 · drawdown 0.0555 · margin 0.001447 · selfCorr 0.6651
- Settings: `region=USA  universe=TOP3000  delay=0  decay=4  neutralization=SUBINDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
add(add(add(zscore(rank(divide(liabilities, assets))), zscore(rank(ts_delta(divide(income, cap), 174)))), multiply(group_zscore(ts_av_diff(close, 10), subindustry), -0.8)), multiply(group_zscore(ts_mean(divide(abs(returns), volume), 20), subindustry), -0.6))
```

## `E5kNGQxL`  D0  AVERAGE
- IS: Sharpe **2.08** · fitness 1.75 · turnover 0.282 · returns 0.2005 · drawdown 0.085 · margin 0.001422 · selfCorr 0.6149
- Settings: `region=USA  universe=TOP3000  delay=0  decay=4  neutralization=INDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
winsorize(
  add(
    if_else(is_nan(vec_avg(shorted_shares_count_all)), 0,
            group_zscore(ts_mean(ts_backfill(vec_avg(shorted_shares_count_all),22),22), industry)),
    multiply(0.02, group_zscore(add(add(
        -group_zscore(ts_mean(returns,5), industry),
        -group_zscore(ts_std_dev(returns,60), industry)),
        -group_zscore(cap, industry)), industry))
  ), std=4)
```

## `1Y751gZm`  D0  EXCELLENT
- IS: Sharpe **2.05** · fitness 3.04 · turnover 0.1054 · returns 0.2757 · drawdown 0.1089 · margin 0.005231 · selfCorr 0.5892
- Settings: `region=USA  universe=TOP3000  delay=0  decay=4  neutralization=NONE  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
add(
  add(
    -zscore(ts_decay_linear(ts_mean(divide(subtract(high, low), multiply(close, volume)), 750), 350)),
    -zscore(ts_decay_linear(ts_av_diff(close, 5), 5))
  ),
  multiply(0.4, -zscore(ts_decay_linear(ts_av_diff(close, 20), 10)))
)
```

## `xAxOWnVW`  D0  AVERAGE  ⭐ **D0 #2**
- IS: Sharpe **2.03** · fitness 1.94 · turnover 0.0144 · returns 0.1138 · drawdown 0.0822 · margin 0.015772 · selfCorr 0.2014
- Settings: `region=USA  universe=TOP200  delay=0  decay=20  neutralization=INDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
hump(signed_power(vector_neut(group_neutralize(group_neutralize(rank(winsorize(ts_delta(est_epsr, 60), std=4)) + rank(winsorize(ts_delta(est_fcf, 60), std=4)) - rank(winsorize(rel_ret_cust + rel_ret_part - rel_ret_comp, std=4)) - rank(winsorize(ts_zscore(returns, 60), std=4)) + rank(winsorize(ts_arg_min(returns, 60), std=4)) - rank(winsorize(ts_av_diff(returns, 750), std=4)) - rank(winsorize(ts_av_diff(vwap/close, 750), std=4)), pv13_r2_min5_3000_sector), subindustry), returns), 0.8), hump=0.1)
```

## `LLRMo5Pv`  D0  AVERAGE
- IS: Sharpe **2.03** · fitness 1.68 · turnover 0.1288 · returns 0.0878 · drawdown 0.0604 · margin 0.001363 · selfCorr 0.6394
- Settings: `region=USA  universe=TOP3000  delay=0  decay=6  neutralization=NONE  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
add(subtract(add(add(add(add(multiply(2, add(add(add(group_zscore(quantile(ts_backfill(multiply(-1, divide(est_capex, est_tot_assets)), 22), driver=gaussian), subindustry), group_zscore(quantile(multiply(-1, ts_delta(close, 500)), driver=gaussian), subindustry)), group_zscore(quantile(ts_backfill(multiply(-1, divide(ts_delta(est_tot_assets, 250), est_tot_assets)), 22), driver=gaussian), subindustry)), group_zscore(quantile(multiply(-1, ts_delta(sharesout, 250)), driver=gaussian), subindustry))), group_zscore(quantile(ts_backfill(divide(sales, cap), 22), driver=gaussian), subindustry)), multiply(6, group_zscore(quantile(ts_backfill(divide(est_grossincome, est_tot_assets), 22), driver=gaussian), subindustry))), group_zscore(quantile(ts_backfill(divide(sales, est_tot_assets), 22), driver=gaussian), subindustry)), multiply(4, group_zscore(quantile(ts_backfill(divide(subtract(est_grossincome, est_capex), est_tot_assets), 22), driver=gaussian), subindustry))), multiply(3, add(group_zscore(quantile(ts_av_diff(close, 5), driver=gaussian), subindustry), group_zscore(quantile(ts_corr(close, volume, 5), driver=gaussian), subindustry)))), multiply(0.75, group_zscore(quantile(divide(ts_mean(volume, 5), ts_mean(volume, 60)), driver=gaussian), subindustry)))
```

## `vRmkVOW3`  D0  AVERAGE
- IS: Sharpe **2.03** · fitness 1.7 · turnover 0.1229 · returns 0.0877 · drawdown 0.0319 · margin 0.001427 · selfCorr 0.603
- Settings: `region=USA  universe=TOP3000  delay=0  decay=10  neutralization=SUBINDUSTRY  truncation=0.012  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
winsorize(if_else(is_nan(group_zscore(ts_mean(ts_backfill(vec_avg(nws12_mainz_short_interest), 22), 22), subindustry)), group_zscore(ts_mean(news_pct_90min, 22), subindustry), 5 * group_zscore(ts_mean(ts_backfill(vec_avg(nws12_mainz_short_interest), 22), 22), subindustry)) - 0.5 * group_zscore(ts_decay_linear(ts_delta(close, 5), 5), subindustry), std=4)
```

## `1Yo2OPjm`  D0  AVERAGE
- IS: Sharpe **2.02** · fitness 1.95 · turnover 0.1138 · returns 0.1168 · drawdown 0.0515 · margin 0.002053 · selfCorr 0.549
- Settings: `region=USA  universe=TOP3000  delay=0  decay=10  neutralization=INDUSTRY  truncation=0.08  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
winsorize(trade_when((ts_rank(abs(news_pct_30min), 60) > 0.152), ts_decay_linear(1.691 * ((rank(implied_volatility_call_60 - implied_volatility_put_60) + rank(ts_delta(implied_volatility_mean_60, 5))) * rank(-1 * ts_zscore(returns, 10))) + 0.501 * rank(snt_value), 35), -1), std=3)
```

## `E5kkmL1L`  D0  GOOD
- IS: Sharpe **2.01** · fitness 2.49 · turnover 0.0494 · returns 0.192 · drawdown 0.095 · margin 0.007776 · selfCorr 0.6828
- Settings: `region=USA  universe=TOP3000  delay=0  decay=4  neutralization=SUBINDUSTRY  truncation=0.02  pasteurization=ON  unitHandling=VERIFY  nanHandling=OFF  instrumentType=EQUITY  language=FASTEXPR  maxTrade=OFF  startDate=2019-01-01  endDate=2023-12-31`
- Expression:
```
add(zscore(ts_mean(subtract(implied_volatility_call_180, implied_volatility_put_180), 20)), group_zscore(divide(sales, cap), subindustry))
```