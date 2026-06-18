# D0 因子挖掘报告 (账号 huyukun662@gmail.com)

## 目标
WorldQuant Brain 上挖掘一个**可提交**的 **delay=0** 因子:简洁、含正则化、
有经济学意义、用冷门算子、规避 IV、且与账号已提交的 19 个 ACTIVE 因子不相关。

## 账号约束 (实测)
- 支持 delay=0 模拟 (旧账号不支持)。
- 算子受限 (TUTORIAL 层 67 个): ts_max/ts_min/ts_skewness/ts_kurtosis/
  ts_entropy/ts_median 等**不可用**。
- 提交门槛 (D0 竞赛 is.checks 限值):
  - LOW_SHARPE   limit = **2.0**
  - LOW_FITNESS  limit = 1.3
  - HIGH_TURNOVER limit = 0.7
  - CONCENTRATED_WEIGHT limit = 0.1
  - SELF_CORRELATION limit = 0.7
- 已提交 19 个 ACTIVE 因子主题: 已实现波动/范围、日内(close-open)矩、
  IV skew、长窗价价相关 ts_corr。**完全未用成交量/流动性**。

## 最佳因子 (核心成果)
```
Expression (FASTEXPR):
  -zscore(ts_decay_linear(ts_mean(divide(subtract(high, low),
          multiply(close, volume)), 750), 350))

Settings: USA, TOP3000, delay=0, neutralization=NONE,
          truncation=0.08, pasteurization=ON, decay=0
```
经济含义: **Amihud 非流动性 → 流动性溢价**。`(high-low)/(close*volume)` =
当日价格振幅 / 当日成交额, 衡量单位成交额引起的价格冲击 (非流动性)。
做空高非流动性 (高冲击/低流动) 的股票, 多空相反 —— 即在 2019-2024 大盘
流动股 (低冲击) 跑赢的环境中获取流动性溢价。750 日均值 + 350 日线性衰减
平滑长期流动性水平。zscore 为横截面正则化。

冷门算子: ts_decay_linear (线性衰减加权)。规避 IV。D0 仅用当日 PV。

## WQ Brain 实测指标 (alpha_id=qMAoxodK)
| 指标 | 值 | 提交门槛 | 通过? |
|---|---|---|---|
| IS Sharpe   | **1.84** | > 2.0 | ✗ |
| IS Fitness  | 2.57 | > 1.3 | ✓ |
| IS Turnover | 0.012 | < 0.7 | ✓ |
| IS Returns  | 0.245 | — | — |
| IS Drawdown | 0.103 | — | — |
| 权重集中度  | 通过 | < 0.1 | ✓ |
| **自相关**  | **~0.48** | < 0.7 | ✓ |

→ **通过除 LOW_SHARPE 外的全部提交检查**, 但 D0 竞赛 Sharpe 门槛为 2.0。

## 关键发现: "SH>2" 与 "不相关" 的冲突
系统挖矿 17 轮 / ~110 次 D0 模拟, 覆盖经济族: 非流动性、低波动/范围、
方差、反转/均值回复、BAB(beta)、隔夜跳空、价量相关、52周高点。

- **凡 SH 有望 >2 的 D0 信号 (范围²/方差/日内矩) 与已提交池 corr≈0.91** ——
  会被 SELF_CORRELATION (limit 0.7) 拦截。 (实测: 收盘方差 corr=0.91)
- **真正不相关 (corr 0.12-0.48) 的信号 (非流动性、反转、流动性) 封顶 SH≈1.84。**

杠杆扫描 (非流动性因子, 全部已测):
- 中性化: NONE(1.84) > MARKET(1.76) > INDUSTRY(1.58) > SUBINDUSTRY(1.49)
- 基础窗口: 250(1.63) < 500(1.72) < **750(1.84)** > 1000(1.74)
- 衰减: 150(1.81) < 250(1.83) < **350(1.84)**
- 截断: **0.08(1.84)** > 0.02(1.74) > 0.15(1.63)
- 宇宙: **TOP3000(1.84)** >> TOP1000(0.97) (流动性溢价在小盘更强, 缩窄宇宙削弱)
- 组合/混合: 均未优于单因子 (强信号同属范围族, 无分散收益)

## 追加挖矿 (用户要求"继续挖更冷门强信号", round 17-19)
继续 ~25 次 D0 模拟, 测试更冷门/正交化的构造, 结论: **SH 1.84 上限稳固**。

1. **ts_regression 残差正交化** (剥离市场共同成分以期降相关却保强度):
   - 残差化范围 → SH -0.05; 残差化非流动性 → 0.04; 残差化方差 → -0.25。
   - **证明"强度"与"相关度"同源**: 范围/方差信号的 Sharpe 来自市场共同成分
     (正是 corr≈0.9 的来源), 剥离它则信号归零。二者无法解耦。
2. **冷门流动性度量** (不同机制, 仍与已提交池不相关):
   - 零收益率 LOT 非流动性 ts_mean(less(abs(returns),0.001)) → SH 0.82
   - stale-price days_from_last_change(close) → SH 1.21
   - Amihud 收益版 |returns|/(close*vol) → SH 0.79 (范围版 1.84 远强, 范围分子是关键)
3. **流动性复合** (Amihud + LOT, 期望正交叠加破2.0):
   - 等权 1.41 / 2:1 1.64 / 3:1 1.75 —— **均 < Amihud 单独 1.84**。
     流动性度量彼此相关 (都做空非流动名), 无分散收益。
4. **冷门聚合/变换**:
   - ts_rank 时序基聚合 → 0.23/0.50 (抹掉持续横截面 level = 信号本身)
   - signed_power(.,1.5) 放大 → SH 1.82, FIT 3.15, RET 0.375
     (放大只抬 fitness/收益, 集中度等比上升, Sharpe 不变)

## 最终结论
本 D0 竞赛 (Sharpe 门槛 2.0) 下, **"通过 submit" 与 "与已提交因子不相关"
存在结构性冲突**: 凡 SH>2 的 D0 PV 信号都属范围/方差/日内矩族 (与账号
已提交 19 因子 corr≈0.9, 被 SELF_CORRELATION 拦), 而真正不相关的经济族
(流动性/反转) 在本宇宙封顶 SH≈1.84。

**交付**: 最强的、满足"简洁+正则化+经济含义+冷门算子+D0+无IV+不相关"
全部定性要求的因子是上文的 Amihud 非流动性因子 (SH 1.84, 通过除 LOW_SHARPE
外全部检查)。它在标准 1.25 门槛下可直接提交; 在本 D0 竞赛的 2.0 门槛下尚差
0.16。
