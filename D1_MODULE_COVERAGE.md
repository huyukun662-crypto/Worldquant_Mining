# D1 数据模块全覆盖结论(account DH58557)

按"换 module + 换结构"方向,系统测试了本账号 USA/delay1 下**全部可用数据模块**,
每个都用该模块最强的已知异象 + 合适结构(修正动量、价值/质量比率、情绪、波动率等)。

## 各模块最高 Sharpe(横截面 L/S,SUBINDUSTRY 中性化)

| 数据模块 | 内容 | 测试结构 | 最高 \|SH\| | 能否过 SH 1.25 |
|---|---|---|:---:|:---:|
| **pv1** | 价量 | 反转 (ts_rank/zscore/dollar-vol) | **2.21** | ✅ 唯一可行 |
| socialmedia12 | 社媒情绪 | level / ts_delta | 0.95 | ❌ |
| option8 | 期权波动率 | IV 趋势 / skew / VRP | 0.84 | ❌ |
| analyst4 | 分析师预测 | EPS 修正动量 / 评级 / 收益率 | 0.75 | ❌ |
| model16 | 基本面综合分 | fscore_* level | 0.68 | ❌ |
| fundamental6 | 原始财报 | EBITDA/EV, ROA, cashflow yield, 杠杆 | 0.25 | ❌ |
| model51 | 风险指标 | beta / 特质波动 | ~0.0 | ❌ |

## 结论

**在此 TUTORIAL 账号上,只有价量(pv1)的"反转"异象能过 SH 1.25。**
所有非价量模块(基本面、分析师、情绪、期权、风险)最高 SH 仅 0.25–0.95,
远达不到门槛 —— 且 `normalize`/decay 等只能抬 fitness、**无法凭空创造 Sharpe**,
所以这些模块即使换结构也过不了。

可能原因(账号档位限制):alt-data 字段在此 tier 的历史/覆盖有限,横截面信号被稀释;
事件型字段(评级)还不支持 rank/ts_delta。`ts_skewness`/`ts_kurtosis`/`vector_neut`
等算子在此账号不可用。

## 已确认可提交因子(全部 pv1 反转族,TOP1000,FIT≥1,8/8 PASS)

| 结构 | 表达式 | FIT | 与基础反转相关 |
|---|---|:---:|:---:|
| ts_rank 短反转 | `rank(-ts_rank(returns,7))` | 1.09 | 1.00 |
| zscore 短反转 | `normalize(-ts_zscore(returns,6))` | 1.01 | 0.91 |
| 美元成交额反转 | `normalize(-ts_rank(multiply(returns,volume),6))` | 1.16 | 0.90 |
| 长周期反转(低相关) | `normalize(-ts_rank(returns,220))` | 1.02 | **0.52** |

要在此账号挖到"非反转 / 跨模块"的可提交因子,需升级账号档位以获得更完整的
alt-data 覆盖,或放开"只 check 不 submit"用平台多因子组合。
