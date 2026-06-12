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

## 第三因子可行性结论(批次 42-44,2026-06-12)

目标:再挖一个与池、与 GroQl8nG、与 58vJ2WZ6 三方相关都 <0.7 的因子。
结论:**当前账号 D0 数据可达性下不可行**,证据链:

1. `pnl_corr.py` 实测 **corr(GroQl8nG, 58vJ2WZ6) = 0.662 < 0.7**,
   两因子可先后提交(先 GroQl8nG,后 58vJ2WZ6 擦线)。
2. 第三家族探针 ×10(批次 42)全弱:股息预估修正 0.73 最高,评级变化
   /新闻漂移/覆盖动量/产业链变体 0.04-0.51。D0 单块 SH>1.0 的引擎
   确认只有三个:反转 1.2 / ern4 1.31 / 修正动量(44d)1.38。
3. 无 ern4 无反转的修正动量+价值混合(批次 43)上限 1.76,且与
   GroQl8nG 相关已达 0.68——GroQl8nG 本身含全部三引擎,任何够到
   2.0 的组合必然与它 >0.7。
4. 修正动量横移到 66d(批次 44)单块 0.04:该信号只活在 44d 窗口,
   无法用周期平移去相关。

## 提交策略(最终建议)

1. 网页端 Submit `GroQl8nG`(SH 2.25 / SC 0.558,边际 0.142)。
2. 提交完成、检查通过后,重查 `58vJ2WZ6` 的 SC(预计 ≈0.662,擦线
   PASS),通过则第二个提交。
3. 不要先提交 58vJ2WZ6:它对池的 SC 已是 0.662,若 GroQl8nG 后提交,
   GroQl8nG 的新 SC = max(0.558, 0.662) = 0.662,两单边际都被压薄。

## 第三因子(修订):D1 路线达成(批次 45-47,2026-06-12)

"D0 不可行"的结论成立,但换 delay 即破局:**D1 的 LOW_SHARPE 门槛是
1.25**(D0 是 2.0),且 D1 анl4 库存有完整的一致预期字段
(`anl4_basicconafv110_*`)。把 D0 验证过的"修正动量+价值"配方(无
ern4、无反转)在 D1 重建,直接过全部检验:

| alpha_id | SH | FIT | TO | SC(池) | corr(GroQl8nG) | corr(58vJ2WZ6) | decay |
|---|---|---|---|---|---|---|---|
| **ZYodPA71**(推荐) | 1.74 | 1.30 | 0.196 | 0.650 | **0.662** | **0.536** | 8 |
| 0m8NmaXr | 1.77 | 1.21 | 0.229 | 0.645 | 0.662 | 0.538 | 6 |
| GroK1ANx(+FCF修正) | 1.64 | 1.36 | 0.170 | 0.667 | 0.661 | 0.551 | 8 |

ZYodPA71 表达式(USA·EQUITY·delay=1·TOP3000·decay=8·SUBINDUSTRY):

```
add(
  multiply(2, rank(ts_backfill(divide(ts_delta(ts_backfill(vec_avg(anl4_basicconafv110_mean), 22), 44), close), 66))),
  group_rank(ts_backfill(divide(ts_delta(ts_backfill(vec_avg(anl4_basicconafv110_mean), 22), 44), close), 66), subindustry),
  rank(divide(cashflow_op, cap)),
  rank(divide(sales, add(cap, subtract(debt, cash)))),
  rank(ts_delta(return_assets, 66)),
  group_rank(ts_mean(rel_ret_comp, 5), industry),
  multiply(0.5, rank(ts_mean(snt_social_value, 5))),
  filter=true)
```

排雷记录:model77 现成修正字段全弱或反向(-0.55~0.23);anl4 一致预期
字段在 D1 改名为 `*conafv110_*`;TOP1000 门槛仍 2.0 且信号衰减
(1.76→0.81);非 USA region 本账号全部无权限;价值加重版(akOQkmbw)
撞池内价值簇 SC 0.724 FAIL——价值权重必须 ≤1。

### 三连提交顺序(最终)

1. `GroQl8nG`(D0,SC 0.558)
2. `58vJ2WZ6`(D0,SC≈0.662 擦线)
3. `ZYodPA71`(D1,提交后 SC≈max(0.650, 0.662, 0.536)=0.662 擦线)

注意:本地 pnl_corr 与平台 SC 的窗口可能有 ±0.02-0.05 偏差,2、3 两单
边际只有 ~0.04,平台在 Submit 时会重算并直接拒绝超限——失败无惩罚,
只占用一次提交槽位。

### 边际加厚尝试(批次 48)——否定,维持 ZYodPA71

把 EPS 修正动量换成多科目修正(EBIT/CFO/净利/股息,`anl4_*_mean`
MATRIX 字段)以压低 corr(GroQl8nG):全部失败。单块 -0.12~0.08(这些
预估水平字段更新频率低,44 日差分是噪声);且去掉社媒/产业链块的
替换组合池 SC 反而超标(1.41/1.35 均 FAIL SELF_CORRELATION)——
`snt_social_value` 和 `rel_ret_comp` 块在 ZYodPA71 里有压低池 SC 的
作用,不可省。三连方案维持不变。
