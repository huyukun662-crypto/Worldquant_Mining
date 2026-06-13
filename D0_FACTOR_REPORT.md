# D0 因子挖掘报告 — 波动率归一化短期反转

账户：`2445560398@qq.com` ｜ 区域：USA ｜ 仅挖 **delay = 0**

## 1. 结论（先说可提交性）

挖出 1 个**通过 WorldQuant Brain 全部提交检查**的 D0 因子（用 `/check` 端点
做 pre-submit 校验，**未实际 submit**）：

```
表达式 : -rank(divide(ts_av_diff(close, 5), ts_std_dev(close, 20)))
设置   : delay=0, universe=TOP500, neutralization=SUBINDUSTRY,
         decay=4, truncation=0.05, pasteurization=ON
```

| IS 指标 | 值 |
|---|---|
| Sharpe | **2.11** |
| Fitness | **1.36** |
| Turnover | 0.234 |
| Returns(年化) | 0.107 |
| Drawdown | 0.069 |
| Long / Short | 247 / 247 |

**`GET /alphas/{id}/check` 提交检查 — 9/9 全 PASS：**

| 检查项 | 结果 | limit | value |
|---|---|---|---|
| LOW_SHARPE | ✅ PASS | 2.0 | 2.11 |
| LOW_FITNESS | ✅ PASS | 1.3 | 1.36 |
| LOW_TURNOVER | ✅ PASS | 0.01 | 0.234 |
| HIGH_TURNOVER | ✅ PASS | 0.7 | 0.234 |
| CONCENTRATED_WEIGHT | ✅ PASS | — | — |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 0.42 | 0.74 |
| IS_LADDER_SHARPE | ✅ PASS | 0.5 | 1.29 |
| **SELF_CORRELATION** | ✅ **PASS** | 0.7 | **0.36** |
| MATCHES_COMPETITION | ✅ PASS | — | — |

> **`SUBMITTABLE = True`** — 全部 9 项检查通过，可以上交。
> 证据见 `WQ_D0_SUBMISSION_CHECK.json`。

## 2. 为什么满足全部要求

| 用户要求 | 本因子如何满足 |
|---|---|
| **只挖 D0** | `delay=0`（本账户层级现已开放 D0 模拟） |
| **通过 submit 检验** | `/check` 9 项全 PASS（D0 门槛：Sharpe>2.0、Fitness>1.3） |
| **简洁** | 1 个核心信号、4 个算子、单一价格字段 |
| **正则化函数** | `rank`（横截面归一化）+ 除以 `ts_std_dev`（波动率归一化） |
| **经济学意义** | 短期过度反应/均值回归溢价（见 §4） |
| **冷门算子** | `ts_av_diff`（偏离移动均值），非常规的 ts_mean/ts_delta |
| **避免 IV 字段** | 纯价格字段 `close`，无任何隐含波动率/期权字段 |
| **与以前不相关** | 自相关 max = **0.36 < 0.7**；账户已有 D0 因子皆为 IV/新闻/空头类，本因子为纯价量反转，经济轴完全不同 |

## 3. 表达式逐层拆解

```
-rank( divide( ts_av_diff(close, 5) , ts_std_dev(close, 20) ) )
        └────────┬────────┘   └────────┬────────┘
   价格相对5日均值的偏离       20日价格波动率（归一化分母）
```

1. `ts_av_diff(close, 5)` = `close - ts_mean(close, 5)`：当前价相对近 5 日锚的**偏离量**——价格短期"跑了多远"。这是冷门算子，直接度量对均值的偏离。
2. `÷ ts_std_dev(close, 20)`：用 20 日波动率把偏离换算成"**几个标准差**"。这是关键的**波动率归一化**，让高波动股与低波动股可比，避免信号被高波动名字主导。
3. `-rank(...)`：横截面排序后**反向**——做多偏离最低（超卖）、做空偏离最高（超买）的股票。

## 4. 经济学含义

这是一个**风险归一化的短期反转 / 过度反应回归**因子：
- 投资者对短期价格冲击（新闻、流动性需求、噪声交易）**过度反应**，价格在数日内回归其内在锚（Lehmann 1990；Jegadeesh 1990；Lo–MacKinlay 1990）。
- 用 20 日波动率归一化偏离，等价于按"信息含量/异常程度"而非绝对价格变动来排序——这正是反转溢价在横截面上最稳健的形式。
- `SUBINDUSTRY` 中性化进一步剥离行业 beta，留下纯粹的个股反转 alpha；`decay=4` 把信号在数日上平滑，将换手压到 0.234，使 Fitness 达 1.36。

## 5. 挖掘过程（如何找到）

参考了 worldquant-miner 等公开 workflow 的"算子 × 字段随机组合 + 设置联调"
思路，但**不复用任何 Alpha101 / 经典因子模板**，从零生成表达式。共 4 批、约
40+ 次 WQ Brain D0 模拟，逐步收敛：

| 批次 | 关键发现 |
|---|---|
| Batch 1（12 候选，探方向） | 价格均值回归方向正确但 Sharpe~1.2；纯流动性(Amihud)/振幅信号方向需反号 |
| Batch 2（调 decay/中性化/universe） | **TOP1000 比 TOP3000 干净得多**；振幅+反转**组合**风险调整最佳 |
| Batch 3（冲 2.0） | **波动率缩放反转** `av_diff(close,5)/std(close,20)` 是最强干净核心，Sharpe 逼近 2.0 |
| Batch 4（精调） | **TOP500 + decay=4 + truncation=0.05** 把 Sharpe 推到 **2.11**、Fitness 到 **1.36**，越过 D0 提交线 |

关键杠杆：universe 收紧到 TOP500、波动率归一化、低 truncation(0.05)、适度 decay。

## 6. 复现方法

```bash
# 一键复现：重新模拟冠军表达式 + 跑完整 /check 提交检查（不会 submit）
python scripts/verify_champion.py        # 输出 9/9 PASS + 落盘 WQ_D0_SUBMISSION_CHECK.json

# 对任意已模拟 alpha 跑 pre-submit 检查
python scripts/check_submit.py <alpha_id>

# 批量挖掘驱动（jobs.json -> 排名表 + JSON）
python scripts/mine_d0.py jobs.json out.json 3
```

> 注：WQ Brain 会回收**未提交**的模拟 alpha，故快照里的 `alpha_id`（如 `z0bQOQ48`）
> 可能过期；但表达式与设置是确定性的，重跑 `verify_champion.py` 必得同样指标。

## 7. 备选因子（亦逼近/达到提交线，留作多样化）

| 表达式 | universe/decay | Sharpe | Turnover | Fitness | 备注 |
|---|---|---|---|---|---|
| `subtract(rank(ts_av_diff((high-low)/close,10)), rank(av_diff(close,5)/std(close,20)))` | TOP500 / d6 / trunc0.05 | 2.08 | 0.190 | 1.39 | 反转 + 日内振幅确认，换手更低、Fitness 更高 |
| `-rank(divide(ts_av_diff(close,5), ts_std_dev(close,22)))` | TOP500 / d4 | 2.03 | 0.222 | 1.33 | 冠军的 std 窗口变体 |
| `-rank(winsorize(divide(ts_av_diff(close,5),ts_std_dev(close,20)),std=4))` | TOP500 / d4 | 2.00 | 0.226 | 1.32 | 显式加 `winsorize` 正则化 |

## 8. 账户 D0 提交门槛（实测自 `/check`，写给后续会话）

- D0 的 `LOW_SHARPE` limit = **2.0**（不是 d1 的 1.25），`LOW_FITNESS` = **1.3**。
- 还需通过 `LOW_SUB_UNIVERSE_SHARPE`、`IS_LADDER_SHARPE`、`CONCENTRATED_WEIGHT`、
  `SELF_CORRELATION`(<0.7)。
- `delay=0` 现已可模拟（旧 CLAUDE.md 记的"Delay 0 not available"已失效）。
- `/correlations/prod` 返回 403（本账户层级无生产相关性权限）。
- 模拟并发上限 ~2–3；并行过猛会持续 429，务必**串行/小并发**。
