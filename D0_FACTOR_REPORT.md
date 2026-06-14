# D0 因子挖掘报告（最终：找到可提交因子）

账户：`2445560398@qq.com` ｜ 区域：USA ｜ 仅 **delay = 0** ｜ 全部数字经 `regular.code == 提交表达式` 核对（`code_match=True`）+ 隔离单跑复验

## 1. 结论：挖到一个通过 D0 submit 检验的因子 ✅

用 `GET /alphas/{id}/check` 做 pre-submit 校验（**未实际 submit**），干净隔离复验确认：

```
add(add(add(add(add(
  zscore(group_zscore(ts_mean(ts_backfill(divide(ebitda,cap),120),60),subindustry)),   # 价值
  multiply(2,  zscore(ts_zscore(divide(volume,sharesout),20)))),                        # 异常换手 ×2
  multiply(1.5,zscore(-rank(returns)))),                                                # 短期反转 ×1.5
  zscore(-rank(ts_mean(divide(abs(returns),multiply(volume,vwap)),20)))),               # Amihud 非流动性
  zscore(-rank(ts_mean(divide(subtract(multiply(2,close),add(high,low)),subtract(high,low)),5)))), # 买卖压力CLV
  zscore(-rank(multiply(ts_av_diff(close,5),ts_rank(volume,20)))))                      # 量加权反转

delay=0, universe=TOP3000, neutralization=SUBINDUSTRY, decay=8, truncation=0.05
```

| IS 指标 | 值 |
|---|---|
| Sharpe | **2.04** (limit 2.0) |
| Fitness | **1.44** (limit 1.3) |
| Turnover | 0.311 |
| Returns(年化) | 0.155 |
| Self-correlation max | **0.669** (limit 0.7) |

**`/check` 8 项全 PASS → `SUBMITTABLE = True`**（含 `LOW_SHARPE`、`LOW_FITNESS`、
`SELF_CORRELATION` 全 PASS）。两次干净隔离复验（decay8: SH 2.04；decay10: SH 2.00/FIT 1.50）均 PASS。

## 2. 经济学含义：多轴正交分散化

单个非 IV 简洁信号的真实天花板只有 ~1.2 Sharpe（见 §4）。要越过 D0 的 2.0 线，
把**多个互相正交的经济轴**各自 z-score 后加和，分散化把风险调整收益抬升到 2.0+。
六个轴（数学上 ~5 个正交弱信号 → Sharpe 翻倍）：

| 轴 | 经济含义 | 权重 | 单轴 SH |
|---|---|---|---|
| 价值 EBITDA-yield（行业中性） | 便宜的股票跑赢 | 1 | 0.82 |
| 异常换手延续 | 换手率异常=关注/流动性冲击→短期延续 | 2 | 1.18 |
| 短期反转 | 过度反应回归（分散化器） | 1.5 | 噪声 |
| Amihud 非流动性 | 流动性溢价 | 1 | 0.67 |
| 买卖压力 CLV 反转 | 日内买盘压力反转 | 1 | 0.61 |
| 量加权反转 | 放量异动的反转 | 1 | 0.86 |

价值提供基本面锚，其余五轴是微结构/流动性/反转簇——账户里现有 D0 因子不含这些
轴，故整体 PnL 与它们低相关（self-corr 0.669<0.7）。

## 3. 是否满足要求

| 要求 | 满足 |
|---|---|
| 只 D0 | ✅ delay=0 |
| 通过 submit 检验 | ✅ /check 8 项全 PASS，SUBMITTABLE=True |
| 正则化函数 | ✅ `zscore`×6 + `group_zscore` + `rank` + `ts_zscore` |
| 经济学意义 | ✅ 价值 + 流动性/换手/反转多轴 |
| 冷门算子 | ✅ `ts_av_diff`、`ts_backfill`、`group_zscore`、`ts_zscore` |
| 避免 IV | ✅ 仅 PV + 基本面(ebitda,cap)，无隐含波动率 |
| 与以前不相关 | ✅ self-corr 0.669 < 0.70 PASS |
| 简洁 | ⚠️ 6 轴组合（用户放宽了"简洁"以换取过 submit；单信号到不了 2.0） |

## 4. 关键发现：单信号天花板 vs 多轴组合

经 25+ 个 code-核对串行测量，**单个非 IV 简洁信号真实天花板约 Sharpe 1.2**：
微结构换手 1.18 / 价值 ebitda/cap 0.82 / 量加权反转 0.86 / Amihud 0.67。
**没有任何简洁单因子能过 D0 的 2.0 线**——这正是账户里 2.0+ 的 D0 因子要么用
IV、要么是 4–6 组件加和的原因。本因子走多轴组合路线达成 2.04。

## 5. 复现 & 注意

```bash
python scripts/verify_champion.py      # 重模拟冠军 + /check，输出 SUBMITTABLE
python scripts/check_submit.py <id>    # 对任意 alpha 跑 pre-submit 检查
python scripts/measure_serial.py j.json out.json   # 严格串行+code核对测量
```

- **margin 偏紧**：Sharpe 2.04 vs 2.0、self-corr 0.669 vs 0.70；WQ 单次模拟有
  ~±0.03 Sharpe 波动。真正点 Submit 前请用 `verify_champion.py` 复跑确认当次 ≥2.0。
- 价值轴是 Sharpe 的必需项，但也是 self-corr 的主要来源（与账户 `blNEelXq`=ebit/cap
  相关 0.65）。降低价值权重会把 Sharpe 拖回 ~1.9。
- 未提交的模拟 alpha 会被 WQ 回收，快照 `alpha_id` 会过期；表达式确定性可复现。

## 6. 早期错误更正（已记录在 CLAUDE.md）

报告早期曾报 Sharpe 2.11/2.27 的"可提交"结果，均为测量 bug：①`simulate_many`
共享 `requests.Session` 跨线程并发→alpha-id 串号；②本执行环境**重复执行后台命令**
+ WQ 并发负载→结果交错。修复：`simulate` 返回 `code_match`，关键测量一律
**串行/前台 + code 核对 + 隔离单跑双次拉取**。

## 7. 换方向探索（均 code-核对，结论：ebitda 锚版仍是唯一全过的）

应"换一个方向重新挖"，系统测了其它经济轴，但都过不了：

| 方向 | 最强单轴 / 组合 | 真实 SH | 为何不行 |
|---|---|---|---|
| 质量/盈利(Novy-Marx 毛利、Sloan 应计、ROA、毛利率) | gross_prof 0.36 | ≤0.37 | D0 太弱，5 轴加和也 <0.7 |
| 新闻(news12: 相对指数收益、振幅、价格反应、量) | news_react 0.39 | ≤0.39 | D0 太弱 |
| 分析师(analyst4 预期修正) | — | — | event 类型字段，`ts_backfill`/算子不支持 |
| **销售收益率锚** `revt/cap` + 微结构簇 | **SH 2.14 / FIT 1.5** | 2.14 | **SELF_CORRELATION=FAIL**（销售收益率与已提交池相关 ≥0.70，比 ebitda 的 0.669 更高；降权重则 SH 跌回 ~1.9） |

**结论**：D0 上够强(0.8–1.2)的非 IV 轴只有**价值 + 微结构簇**；质量/新闻/分析师在 D0
都 ~0.3 太弱。能同时过 `Sharpe>2.0` 且 `self-corr<0.7` 的，只有 §1 的
**ebitda 收益率锚 + 微结构** 组合（self-corr 0.669）。销售收益率虽更强(2.14)却踩
自相关红线。故 §1 因子是本账户约束下的唯一解。
