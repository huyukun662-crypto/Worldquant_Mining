# D0 因子挖矿分析报告

账号 `huyukun662@gmail.com`（ID `YW92315`）。本轮**只挖 delay=0 因子**，全部用
WorldQuant Brain `/simulations` 回测，再用 `/alphas/{id}/check` 预提交校验。
**未执行任何 Submit 操作**——仅确认是否可提交。

## 1. 关键事实：本账号 D0 可用

旧 `CLAUDE.md` 记录的是另一账号无 delay=0 权限。本账号实测 `delay=0`
在 `/simulations` 正常返回，TOP200/500/1000/3000 均可。

## 2. D0 提交门槛（实测自 `/check`，比 D1 严格得多）

| 检查项 | 门槛 | 说明 |
|---|---|---|
| LOW_SHARPE | **Sharpe > 2.0** | D0 的硬门槛（D1 仅需 1.25），最难达标 |
| LOW_FITNESS | Fitness > 1.3 | |
| LOW_TURNOVER / HIGH_TURNOVER | 0.01 < TO < 0.7 | |
| CONCENTRATED_WEIGHT | 权重不可过度集中 | zscore 类因子易触发 |
| LOW_SUB_UNIVERSE_SHARPE | 动态下限 | |
| SELF_CORRELATION | 与已提交池低相关 | 提交时才算 |

## 3. 工作量

`scripts/d0_miner.py`（并发提交 + 轮询 + 预提交校验）共跑 **20 批、123 个唯一
D0 因子**，系统性扫过：decay、中性化（NONE/MARKET/INDUSTRY/SUBINDUSTRY）、
universe（TOP200~3000）、truncation、稳健算子（ts_rank/ts_av_diff/signed_power/
vector_neut）、以及多种正交信号源。

## 4. 当前最优因子（通过除 LOW_SHARPE 外的所有 check）

```
add(multiply(2, rank(signed_power(-ts_delta(close, 3), 1.5))),
    rank(-ts_delta(close, 1)),
    rank(-ts_delta(close, 10)),
    rank(divide(cashflow_op, cap)),
    rank(divide(sales, add(cap, subtract(debt, cash)))),
    rank(ts_delta(return_assets, 66)))
```
settings: `USA, delay=0, TOP3000, decay=6, SUBINDUSTRY, truncation=0.08, pasteurization=ON`

- **Sharpe 1.81, Fitness 1.31, Turnover 0.317, 年化 16.5%, 回撤 12.4%**
- 经济学含义：短周期价格反转（1/3/10 日，反转分量加权）+ 经营现金流收益率
  (cashflow_op/cap) + 销售/企业价值 (sales/EV) + ROA 改善 (ΔROA)。
- 正则化：全程 `rank`，`signed_power(·,1.5)` 强化反转尾部；子行业中性化。
- 唯一未过：**LOW_SHARPE（1.81 < 2.0）**。

## 5. 核心结论

在本账号 D0、USA universe 下，**简洁且有经济学意义的因子族稳健封顶于
Sharpe ≈ 1.8**。123 个因子中 26 个 Sharpe≥1.7，**0 个达到 2.0**。

已验证无效的提 Sharpe 杠杆：
- decay（6-7 为 Sharpe 峰值；12-16 把 Fitness 提到 1.45-1.49 但 Sharpe 降到 1.65）
- 中性化（NONE 在该 universe 反而最差 0.84；SUBINDUSTRY 最优）
- 更小 universe（TOP500/1000 上基本面失效，降到 1.0）
- 正交信号叠加：12-1 动量、EV/EBIT 价值、流动性缩放、隔夜跳空/日内位置反转、
  新闻情绪、社媒情绪、分析师预期修正——均未带来正分散化增益（多为弱信号或
  与反转相关，部分反而抬高换手拉低 Sharpe）。

本账号 D0 可用的非 IV 正交另类数据有限（无做空兴趣/机构持仓 D0 切片；
期权/earnings4 多为 IV，按要求规避）。要把 Sharpe 顶到 2.0 需要一个本族之外的
数据边际优势。
