# D0 低自相关可提交因子 — 最终结果(批次 32-41)

目标:在 58vJ2WZ6(SH 2.18 / SC 0.662,距 0.7 上限仅 0.038)基础上,
挖出**自相关显著更低**的 D0 可提交因子。结果:SC 从 0.662 降到
**0.558**(安全边际 0.142,扩大 3.7 倍),Sharpe 反而更高。

## 推荐提交:alpha_id `GroQl8nG`

```
add(
  multiply(2, rank(ts_backfill(vec_avg(ern4_erneffct1), 66))),
  multiply(2, rank(ts_backfill(divide(ts_delta(ts_backfill(vec_avg(anl4_basicconaf_mean), 22), 44), close), 66))),
  multiply(0.75, rank(ts_backfill(divide(subtract(vec_avg(anl4_basicconaf_pu), vec_avg(anl4_basicconaf_down)), add(vec_avg(anl4_basicconaf_numest), 1)), 66))),
  multiply(1.25, group_rank(-ts_delta(close, 5), industry)),
  group_rank(ts_mean(rel_ret_comp, 5), industry),
  multiply(0.5, rank(ts_mean(snt_social_value, 5))),
  filter=true)
```

设置:`USA · EQUITY · delay=0 · TOP3000 · decay=8 · SUBINDUSTRY ·
truncation=0.08 · pasteurization=ON · unitHandling=VERIFY · nanHandling=OFF`

### 预提交 check(2026-06-11 两次复核一致)

| 检查项 | 结果 | 门槛 | 实际值 |
|---|---|---|---|
| LOW_SHARPE | **PASS** | > 2.0 | **2.25** |
| LOW_FITNESS | **PASS** | > 1.3 | **1.76** |
| LOW/HIGH_TURNOVER | PASS | 0.01–0.7 | 0.187 |
| **SELF_CORRELATION** | **PASS** | < 0.7 | **0.5581** |
| LOW_SUB_UNIVERSE_SHARPE | PASS | — | PASS |
| CONCENTRATED_WEIGHT | PASS | — | — |
| MATCHES_COMPETITION | PASS | — | Challenge / IQC2026S2 |
| UNITS | WARNING(rank 求和无量纲,惯例提示,不阻塞) | — | — |

其他:年化收益 11.5%,回撤 6.9%,多 1564 / 空 1502,margin 12.3bps。

### 六个分量的经济学含义

1. **盈余公告效应**(`ern4_erneffct1`,权重 2):PEAD,事件驱动主引擎。
2. **分析师预估修正动量**(权重 2,本轮新发现的第二引擎):44 日 EPS 一致
   预期变化 / 股价。单块 SH 1.38、**单块自相关仅 0.161**——与已提交池
   几乎完全正交,是把 SC 从 0.66 拉到 0.56 的核心功臣。
3. **预估上调广度**(pu−down)/numest(权重 0.75):修正动量的"广度"
   确认,与"幅度"互补。
4. **行业内 5 日反转**(权重 1.25):唯一的价格桥块。剂量经 0.75/1/1.25
   梯度实测,1.25× 在 decay 8 下 Sharpe-SC 权衡最优。
5. **竞争对手动量溢出**(`rel_ret_comp`):产业链 lead-lag。
6. **社媒情绪**(`snt_social_value`,权重 0.5):辅助。

### 全部 6 个过线变体(均可提交)

| alpha_id | 反转剂量 | decay | SH | FIT | TO | SC |
|---|---|---|---|---|---|---|
| **GroQl8nG**(推荐) | 1.25× | 8 | **2.25** | **1.76** | 0.187 | **0.5581** |
| d5Q9jAxX | 1× | 6 | 2.25 | 1.62 | 0.215 | 0.5600 |
| 2rKGlmNx(最简,4 分量) | 1× | 6 | 2.15 | 1.59 | 0.197 | 0.5557 |
| qMX5j2NE | 0.75× | 4 | 2.23 | 1.44 | 0.257 | 0.5598 |
| 9qRGXlVK | 0.75×(subindustry) | 6 | 2.20 | 1.57 | 0.212 | 0.5655 |
| WjgY7nxj | 0.75× | 6 | 2.18 | 1.56 | 0.207 | 0.5654 |

注意:GroQl8nG 与 58vJ2WZ6 共享 ern4 块,**两者都提交的话互相之间会有
相关性**;若计划双提交,先提交 GroQl8nG(SC 边际大),再用提交后重算的
SC 决定 58vJ2WZ6 是否仍过 0.7。

## 本轮方法论(批次 32-41,~75 次仿真)

关键工具发现:`GET /alphas/{id}/correlations/self` 对任何已仿真 alpha
直接返回与已提交池逐一的相关性(不被 LOW_SHARPE 短路),使 SC 可以
作为搜索目标而非事后惊喜。

已提交池(19 个 OS alpha)聚类:IV 价差簇、低波/波动不对称簇(May-14
一批)、ts_corr 价格结构簇、反转+价值复合簇。SC 归因实测:

| 块 | 单块 SH | 单块 max SC | 撞哪个簇 |
|---|---|---|---|
| 预估修正动量(44d) | 1.38 | **0.161** | 无 |
| ern4 盈余效应 | 1.25-1.31 | 0.466 | 弱撞低波 |
| 预估广度 | 0.45 | 0.502 | 低波簇 |
| 回购授权/cap | 0.69 | **0.722** | 价值簇(j21EEbx9 含 sales/cap)|
| sales/EV、cashflow/cap | — | ~0.67 | 价值簇(blNMGwZR)|

死路清单(全部实测否定):空头持仓异象(2019+ 反向,-0.74)、12-1
动量(0.03,动量崩盘期)、SUE via news_eps_actual(财期错位)、
多周期修正动量堆叠(只有 44d 有效)、vector_neut 硬正交(信号一起
投影掉,1.65→0.45)、trade_when 波动门控(2.25→1.94)、STATISTICAL
中性化(账号层级不可用)、经典基本面异象 D0 全弱(应计/增发/资产
增长/毛利 0.09-0.48)。

结论路径:去掉价值块(SC 0.67→0.63)→ 换上修正动量第二引擎
(0.63→0.59)→ 反转剂量精调 1.25×@decay8(SH 1.79→2.25,SC 0.558)。
