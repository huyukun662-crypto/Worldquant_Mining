# D0 可提交因子 — 最终结果

账号 `huyukun662@gmail.com`（ID `YW92315`），全部经 WQ Brain `/simulations`
回测 + `GET /alphas/{id}/check` 预提交校验。**按要求未执行 Submit**，
可提交性已确认，等待用户自行提交。

## 推荐提交：alpha_id `58vJ2WZ6`

```
add(
  multiply(2, group_rank(-ts_delta(close, 3), industry)),
  group_rank(-ts_delta(close, 1), industry),
  group_rank(-ts_delta(close, 10), industry),
  multiply(1.5, rank(ts_backfill(vec_avg(ern4_erneffct1), 66))),
  multiply(0.5, rank(divide(ts_backfill(authorized_stock_buyback_amount, 252), cap))),
  rank(divide(cashflow_op, cap)),
  rank(divide(sales, add(cap, subtract(debt, cash)))),
  rank(ts_delta(return_assets, 66)),
  filter=true)
```

设置：`USA · EQUITY · delay=0 · TOP3000 · decay=4 · SUBINDUSTRY ·
truncation=0.08 · pasteurization=ON · unitHandling=VERIFY · nanHandling=OFF`

### 预提交 check（2026-06-11 复核，两次一致）

| 检查项 | 结果 | 门槛 | 实际值 |
|---|---|---|---|
| LOW_SHARPE | **PASS** | > 2.0 | **2.18** |
| LOW_FITNESS | **PASS** | > 1.3 | **1.54** |
| LOW_TURNOVER / HIGH_TURNOVER | PASS | 0.01–0.7 | 0.354 |
| CONCENTRATED_WEIGHT | PASS | — | — |
| LOW_SUB_UNIVERSE_SHARPE | PASS | > 0.94 | 1.44 |
| SELF_CORRELATION | PASS | < 0.7 | 0.662 |
| MATCHES_COMPETITION | PASS | — | Challenge / IQC2026S2 |
| UNITS | WARNING（仅提示，rank 求和无量纲，不阻塞提交） | — | — |

其他指标：年化收益 ~17%，回撤 ~8%，多头 ~1550 / 空头 ~1515（满覆盖）。

### 经济学含义（8 个分量，每项有明确逻辑）

1. **行业内短期反转**（1/3/10 日，3 日加权 2 倍）：行业内超涨/超跌的过度
   反应回归——流动性提供者补偿；`group_rank` 把信号限定为行业内相对排序，
   天然正则化且不受行业β污染。
2. **盈余公告效应**（`ern4_erneffct1`，66 日回填，权重 1.5）：盈余事件
   信息扩散缓慢（PEAD 异象），事件驱动、与价格反转簇低相关——是把
   Sharpe 从 1.86 推过 2.0 的关键正交分量。
3. **回购授权收益率**（`authorized_stock_buyback_amount/cap`，冷门脚注
   字段）：管理层回购授权 = 内部人价值信号（回购异象）。
4. **经营现金流收益率**（cashflow_op/cap）：现金流口径的价值因子，比
   盈利更难操纵。
5. **销售/企业价值**（sales/EV，EV=cap+debt−cash）：对亏损公司也稳健的
   价值口径。
6. **ROA 改善**（66 日 ΔROA）：盈利质量动量（Piotroski 式）。

### 正则化与冷门算子

- 正则化：所有分量 `rank`/`group_rank` 到 [0,1]，天然抗离群值；
  稀疏字段 `ts_backfill`；`add(..., filter=true)` 防 NaN 传播。
- 冷门算子/字段：`group_rank`、`ts_backfill`、`vec_avg`（VECTOR 聚合）、
  `ern4_erneffct1`（盈余效应模型）、`authorized_stock_buyback_amount`
  （报表脚注）。**完全未用任何 IV/隐含波动率字段**。

### 备选（同族，全部 check 通过，decay 换 Fitness↔自相关边际）

| alpha_id | decay | Sharpe | Fitness | TO | 自相关 |
|---|---|---|---|---|---|
| mLXalRj9 | 3 | 2.19 | 1.43 | 0.418 | 0.643 |
| **58vJ2WZ6**（推荐） | 4 | 2.18 | 1.54 | 0.354 | 0.662 |
| O09WgWeb | 5 | 2.17 | 1.65 | 0.307 | 0.680 |
| Grom9d23 | 6 | 2.16 | 1.74 | 0.272 | 0.694 ⚠ 边际仅 0.006 |

⚠ decay ≥ 6 的版本自相关逼近/超过 0.7（用户已提交池中有一个高 decay 的
近亲因子）；提交时 SELF_CORRELATION 会重算，建议选 decay 4 留足边际。

## 挖矿过程纪要（31 批 / 183 个唯一 D0 因子）

- D0 的 LOW_SHARPE 门槛是 **2.0**（D1 仅 1.25）——最硬卡点。
- 单一信号封顶：反转 1.2、价值 0.95、情绪 0.5。
- 「反转+价值+质量」组合封顶 **1.8**，持续 ~30 个变体不破。
- `group_rank(..., industry)` 行业内反转 +0.05 → 1.86。
- **决定性一步**：earnings4 的非 IV 字段 `ern4_erneffct1`（单因子 SH 1.25 /
  TO 0.04，事件驱动低相关）并入后 1.91；再加回购授权项 → **2.16-2.19**。
- 教训：同质信号堆叠收益递减；突破靠真正正交的数据源（事件类 vs 价格类）。
