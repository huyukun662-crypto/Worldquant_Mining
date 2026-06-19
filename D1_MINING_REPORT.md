# D1 因子挖掘报告 — 通过 Submit 检验的因子

## 结论:已确认可提交的因子

```
表达式:    rank(-ts_rank(returns, 5))
alpha_id:  e7OJnAYJ
设置:      USA · TOP1000 · delay=1 · decay=16 · SUBINDUSTRY · truncation=0.08
```

**IS 表现(WQ Brain /simulations,2019-01-01 → 2023-12-31):**

| 指标 | 值 |
|---|---|
| Sharpe | **2.14** |
| Fitness | **1.01** |
| Turnover | **0.6246** |
| Returns(年化) | 14.03% |
| Drawdown | 4.55% |
| Long / Short | 482 / 482 |

**Submission Check(`GET /alphas/e7OJnAYJ/check`,未实际 submit):全部 8 项 PASS**

| 检查 | 结果 | 值 / 限制 |
|---|---|---|
| LOW_SHARPE | PASS | 2.14 > 1.25 |
| LOW_FITNESS | PASS | 1.01 ≥ 1.0 |
| LOW_TURNOVER | PASS | 0.625 > 0.01 |
| HIGH_TURNOVER | PASS | 0.625 < 0.70 |
| CONCENTRATED_WEIGHT | PASS | — |
| LOW_SUB_UNIVERSE_SHARPE | PASS | 1.59 > 1.13 |
| SELF_CORRELATION | PASS | 0.3128 < 0.70 |
| MATCHES_COMPETITION | PASS | — |

→ **SUBMITTABLE(无任何 FAIL)。** 满足用户要求:D1(delay=1)、简洁(单行)、未用 TOP3000(用 TOP1000)、且通过 submit 检验。

## 因子逻辑

`ts_rank(returns, 5)` 把每只股票当日收益在过去 5 日中的相对位置归一化到 [0,1];取负并做横截面 `rank`,即**短期反转**:近 5 日相对走强的股票做空、走弱的做多。`decay=16` 做线性衰减平滑,把换手率压到 0.70 以下,同时把 Sharpe 与 Fitness 抬到门槛之上。SUBINDUSTRY 中性化剔除行业暴露。

为什么 `ts_rank` 版本能过、而 `rank(-returns)` 不能:`ts_rank` 的时序归一化让信号更平滑、收益/换手比更高,decay16 下 Fitness=1.01 越过 1.0;裸 `rank(-returns)` 的 Fitness 结构性卡在 ~0.86(见下方扫描)。

## 挖掘流程(本次实际执行)

平台回测是唯一权威口径。本账号为 TUTORIAL 档,单次 delay=1 模拟约 10–15 分钟,并发约 4。共跑约 50 次模拟,分 7 批:

| 批次 | 思路 | 最佳结果 |
|---|---|---|
| 1 | 纯价格反转 (ts_delta/ts_mean/ts_zscore) | SH≤0.96,Fitness 不足 |
| 2 | 量价交互 (ts_corr, volume-weighted reversal) | SH≤0.93 |
| 3 | model16 基本面综合分 (fscore_*) | 换手极低(0.10)但 SH≤0.68 |
| 4 | 分析师修正/动量衍生分、低 Beta | 均偏弱 |
| 5 | value+momentum 等组合 | SH≤0.68 |
| 6 | **反转的 decay/universe 扫描** | **`rank(-ts_rank(returns,5))` decay16 → SH 2.14 / FIT 1.01 ✓** |
| 7 | `rank(-returns)` truncation 扫描 | Fitness 顶到 0.90,仍 <1.0 |

关键发现:
- 在本账号 USA/delay1/中性化 L/S 上,单字段基本面/量价信号 Sharpe 普遍 0.2–1.0,达不到 1.25。
- **短期反转是唯一稳定越过 1.25 的简洁信号**;`rank(-returns)` decay8 已 SH 1.53、TO 0.63,但 Fitness 卡 0.86(反转收益/换手比结构上限)。
- 改用 `ts_rank(returns,5)` 时序归一 + decay16,Fitness 升到 1.01,全部检查通过。

## Submit 门槛(本账号实测)

Fitness = Sharpe × √(|returns| / max(turnover, 0.125))。Submit 需同时:
Sharpe ≥ 1.25、Fitness ≥ 1.0、turnover ∈ [0.01, 0.70]、子 universe Sharpe ≥ 限值、
权重不过度集中、自相关 < 0.70。

## 复现

```bash
python scripts/run_batch6.py          # 反转 decay 扫描(产出 winner)
python scripts/check_submit.py e7OJnAYJ   # 确认可提交,不实际 submit
```

工具:`scripts/d1_miner.py`(提交+轮询+并发)、`scripts/check_submit.py`
(跑 `/alphas/{id}/check`,确认可提交但不 submit)。
