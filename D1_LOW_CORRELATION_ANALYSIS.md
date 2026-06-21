# D1 低相关因子挖掘 — 分析与结论

目标:在已确认可提交的反转因子之外,挖出**与之低相关(自相关 < 0.70)且同样能过 submit** 的新因子。

## 基准因子(已确认可提交)

```
#1  rank(-ts_rank(returns, 5))   USA·TOP1000·delay1·decay16·SUBINDUSTRY·trunc0.08
    SH 2.14 · FIT 1.01 · TO 0.625 · 自相关 0.31 · 8/8 checks PASS   (alpha e7OJnAYJ)
```

## 核心发现:相关性 vs Fitness 的硬性权衡

本账号上,**只有短期反转家族能越过 fitness ≥ 1.0 这道门槛**。我系统扫描了
~110 次平台模拟(batch1–13),结论是一条清晰的权衡前沿:

### 1) 能过门槛的反转变体,彼此高度相关(都 > 0.70)

不同窗口/中性化的反转,日 PnL 相关矩阵:

|                         | r5 (winner) | r10 | r22 |
|-------------------------|:---:|:---:|:---:|
| r5 `rank(-ts_rank(returns,5))`  | 1.00 | 0.84 | 0.71 |
| r10 `rank(-ts_rank(returns,10))`| 0.84 | 1.00 | 0.92 |
| r22 `rank(-ts_rank(returns,22))`| 0.71 | 0.92 | 1.00 |

- 同表达式换中性化:SUBINDUSTRY vs INDUSTRY 相关 **0.95**;vs MARKET/SECTOR 同样 >0.9。
- 换 decay、换 universe 也都 >0.7。→ **换参数无法降相关。**

### 2) 要把相关性压到 0.70 以下,必须拉长反转周期 —— 但 fitness 顶在 ~0.98

`rank(-ts_rank(returns, N))`,横截面相关随 N 增大单调下降,fitness 先升后稳:

| N (周期) | 与 winner 相关 | 最佳 SH | 最佳 Fitness | 能否 submit |
|:---:|:---:|:---:|:---:|:---:|
| 5   | 1.00 | 2.14 | **1.01** | ✅ (基准) |
| 22  | 0.71 | 1.69 | 0.95 | ❌ fitness |
| 40  | 0.65 | 1.51 | 0.84 | ❌ fitness |
| 60  | 0.63 | 1.41 | 0.77 | ❌ fitness |
| 120 | 0.61 | 1.68 | 0.93 | ❌ fitness |
| 200 | ~0.55 | 1.59 | 0.97 | ❌ fitness |
| **250** | **0.51** | 1.57 | **0.98** | ❌ fitness(差 0.02)|
| 300 | ~0.50 | 1.51 | 0.95 | ❌ fitness |

**returns-250 (decay≈24, SUBINDUSTRY) 是最优解:与 winner 相关仅 0.51、SH 1.57,
但 Fitness 顶在 0.98**(对 decay {16,20,22,24,28} × trunc {0.08,0.10,0.12,0.15}
全部扫过,均 0.96–0.98,过不去 1.0)。

**为何 0.98 是硬上限**:Fitness = SH·√(|ret|/max(TO,0.125))。长周期反转的年化
收益 ret≈16%、SH≈1.55、TO≈0.40 三者强耦合 —— decay 降 TO 的同时同比例压 SH,
乘积封顶。NONE 中性化能把 TO 压到 0.07(< 0.125 floor)使 Fitness 飙到 1.7,
但市场方向暴露又把 SH 锁死在 ~0.94(过不了 LOW_SHARPE)。两端都差一口气。

### 3) 与反转正交的家族,信号太弱、远不到 SH 1.25

| 家族 | 最佳 \|SH\| | 结论 |
|---|:---:|---|
| 动量 (6m/12m price, ts_rank(returns,250)) | ≤0.27(动量为负) | 失败 |
| 基本面综合分 fscore_value/quality/total/… | ≤0.68 | 失败 |
| 分析师修正/多因子衍生分 (model16) | ≤0.46 | 失败 |
| 低波 (ts_std_dev, unsystematic_risk) | ≈0 | 失败 |
| 低 Beta (beta_*_spy) | ≈0 | 失败 |
| 量价 (ts_corr(close,volume,·), volume-weighted reversal) | ≤0.93 | 失败 |
| **社媒情绪** (socialmedia12: scl12_sentiment/snt_value/buzz, cov 1.0) | ≤0.95 (FIT≤0.22) | 失败 |
| **期权波动率** (option8: IV skew / VRP / IV 趋势, cov 0.97) | ≤0.84 | 失败 |

这些虽与反转正交(相关接近 0),但 SH 远低于 1.25,无法独立通过 submit。
**已覆盖该账号全部主要数据家族**(价量、基本面 fundamental6/model16、分析师
analyst4、风险 model51、社媒 socialmedia12、期权 option8)—— 仅短期反转一族能过
SH 1.25,且其所有变体彼此相关 >0.70。

### 5) 单表达式"复合/混合"也救不回来(关键)

试图在**一个表达式内**把反转与正交信号线性组合(理论上分散化可同时保高
Sharpe、降相关):

| 构造 | 最佳 SH | 说明 |
|---|:---:|---|
| `add(rank(rev), rank(fscore))` 各种权重 | ≤0.73 | rank 相加,反转被慢信号淹没 |
| `add(k·zscore(rev), zscore(fscore))` k=1..4 | 0.39–0.73 | zscore 归一仍崩;fscore 覆盖不全把票池锁成慢信号(TO 卡 0.10)|
| `add(2·zscore(rev), zscore(unsystematic_risk))` 全覆盖 | **0.15** | 即便全覆盖、TO 0.42,SH 仍崩到 0.15 |

**根因**:在单个 FASTEXPR 里"信号相加"≠"组合两个组合的 PnL"。表达式相加后
只形成**一个**组合,反转那条脆弱的 `ts_rank` 排序被任何额外信号(哪怕是噪声)
破坏,Sharpe 灾难性下降。真正的分散化(Sharpe 按平方和叠加)只在
**分别提交两个 alpha、由平台在组合层面叠加**时成立 —— 那是另一个动作,不是
单表达式能实现的。

## 结论

**在该 TUTORIAL 账号 + "简洁单表达式 D1" 的约束下,不存在同时满足
(a) 通过全部 submit 检验 与 (b) 与反转基准因子相关 < 0.70 的第二个因子。**
两个要求直接冲突:能过 fitness 的都是短反转(相关 >0.70),而相关 <0.70 的
(长周期反转 / 正交家族)都过不了 fitness/sharpe。

最接近的"低相关候选"(经 batch18–21 细化,大幅优于早期的 r120):

```
rank(-ts_rank(returns, 250))  decay24·SUBINDUSTRY·TOP1000   (alpha omK2rkWb)
  与基准相关 0.51 (<< 0.70 ✓) · SH 1.57 · TO 0.43 · FIT 0.98
  仅差 LOW_FITNESS 一项 (0.98 < 1.0,差 0.02)
```

### 4) 跨区域去相关也不可行

另一条天然去相关路径是"同配方换市场"(EUR/ASI/CHN 的反转与 USA 近乎零相关)。
实测本账号 `/data-sets` 仅 **USA** 可用(EUR/ASI/CHN/GLB/JPN/HKG/… 全部返回 0),
故跨区域方案在此账号上不可用。

## 可行的下一步(需放宽约束)

1. **分别提交两个 alpha**(而非单表达式复合):提交反转 winner + 一个正交弱信号
   (如 `rank(fscore_value)`),由平台在**组合层面**叠加。这是唯一能真正分散化、
   把组合自相关降到 0.70 以下的途径(单表达式复合已实测全部崩溃,见 §5)。
   注意:此账号 Submit Alpha 配额为 1 并发,且本任务约定"只 check、不 submit"。
2. **更高账号档位 / delay 选项**:开放更多字段或 delay=0,正交家族可能达标。
3. **接受 r120 作为低相关因子**并单独调参冲 fitness(目前 0.90,需 +0.10)。

## 复现

```bash
python scripts/run_batch8.py    # 不同字段/周期的反转
python scripts/run_batch10.py   # 正交家族(动量/低波/低beta/量价)
python scripts/run_batch13.py   # 长周期反转冲 fitness
python scripts/corr_matrix.py e7OJnAYJ gJ1v12MJ omK2N3Jb KPbeEoZx e7OA37LJ  # 相关矩阵
```
