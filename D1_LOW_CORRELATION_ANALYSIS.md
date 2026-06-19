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

### 2) 要把相关性压到 0.70 以下,必须拉长反转周期 —— 但 fitness 随之跌破 1.0

`rank(-ts_rank(returns, N))` decay16,随 N 增大:

| N (周期) | 与 winner 相关 | SH | Fitness | 能否 submit |
|:---:|:---:|:---:|:---:|:---:|
| 5   | 1.00 | 2.14 | **1.01** | ✅ (基准) |
| 22  | 0.71 | 1.69 | 0.95 | ❌ fitness |
| 40  | 0.65 | 1.51 | 0.84 | ❌ fitness |
| 60  | 0.63 | 1.41 | 0.77 | ❌ fitness |
| **120** | **0.61** | 1.54 | 0.90 | ❌ fitness |

对 r120 进一步扫 decay {16,24,32,48} 与 trunc {0.08,0.12,0.15}:fitness 顶在
**0.90**(decay16),更高 decay 反而下降。长周期反转的 fitness 存在 ~0.90 的结构上限。

### 3) 与反转正交的家族,信号太弱、远不到 SH 1.25

| 家族 | 最佳 \|SH\| | 结论 |
|---|:---:|---|
| 动量 (6m/12m price, ts_rank(returns,250)) | ≤0.27(动量为负) | 失败 |
| 基本面综合分 fscore_value/quality/total/… | ≤0.68 | 失败 |
| 分析师修正/多因子衍生分 (model16) | ≤0.46 | 失败 |
| 低波 (ts_std_dev, unsystematic_risk) | ≈0 | 失败 |
| 低 Beta (beta_*_spy) | ≈0 | 失败 |
| 量价 (ts_corr(close,volume,·), volume-weighted reversal) | ≤0.93 | 失败 |

这些虽与反转正交(相关接近 0),但 SH 远低于 1.25,无法独立通过 submit。

## 结论

**在该 TUTORIAL 账号 + "简洁单表达式 D1" 的约束下,不存在同时满足
(a) 通过全部 submit 检验 与 (b) 与反转基准因子相关 < 0.70 的第二个因子。**
两个要求直接冲突:能过 fitness 的都是短反转(相关 >0.70),而相关 <0.70 的
(长周期反转 / 正交家族)都过不了 fitness/sharpe。

最接近的"低相关候选":

```
rank(-ts_rank(returns, 120))  decay16·SUBINDUSTRY·TOP1000   (alpha e7OA37LJ)
  与基准相关 0.61 (< 0.70 ✓) · SH 1.54 · TO 0.46 · FIT 0.90
  仅差 LOW_FITNESS 一项 (0.90 < 1.0)
```

### 4) 跨区域去相关也不可行

另一条天然去相关路径是"同配方换市场"(EUR/ASI/CHN 的反转与 USA 近乎零相关)。
实测本账号 `/data-sets` 仅 **USA** 可用(EUR/ASI/CHN/GLB/JPN/HKG/… 全部返回 0),
故跨区域方案在此账号上不可用。

## 可行的下一步(需放宽约束)

1. **复合表达式**(非单算子):把短反转与一个正交弱信号按风险预算线性组合,
   理论上可在保留 fitness 的同时降相关 —— 但已超出"简洁单表达式"约束。
2. **更高账号档位 / delay 选项**:开放更多字段或 delay=0,正交家族可能达标。
3. **接受 r120 作为低相关因子**并单独调参冲 fitness(目前 0.90,需 +0.10)。

## 复现

```bash
python scripts/run_batch8.py    # 不同字段/周期的反转
python scripts/run_batch10.py   # 正交家族(动量/低波/低beta/量价)
python scripts/run_batch13.py   # 长周期反转冲 fitness
python scripts/corr_matrix.py e7OJnAYJ gJ1v12MJ omK2N3Jb KPbeEoZx e7OA37LJ  # 相关矩阵
```
