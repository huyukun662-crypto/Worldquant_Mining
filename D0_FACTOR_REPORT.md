# D0 因子挖掘报告（最终、code-核对版）

账户：`2445560398@qq.com` ｜ 区域：USA ｜ 仅 **delay = 0** ｜ 全部数字经 `regular.code == 提交表达式` 核对（`code_match=True`）

## 1. 总体结论（不回避）

**未能挖到通过 D0 submit 检验的简洁因子。** D0 提交门槛是 Sharpe>2.0 + Fitness>1.3。
在用户约束（非 IV、简洁、含正则化、有经济学含义、与已有因子低相关）下，经 25+
个候选的严格串行 + `code_match` 核对测量，**所有简洁单/双信号的真实天花板约
Sharpe 1.2**：

| 路径 | 最强表达式 | 真实 SH | FIT | TO | 越线？ |
|---|---|---|---|---|---|
| **微结构（用户选定路径）** | `rank(ts_zscore(divide(volume,sharesout),20))` TOP3000 d4 | **1.18** | 0.37 | 0.54 | ❌ |
| 跨轴组合 | `add(-rank(returns), group_zscore(ts_mean(ts_backfill(ebitda/cap,120),60),subindustry))` TOP3000 d8 | 0.96 | **0.87** | 0.072 | ❌ |
| 基本面单 ratio | `group_zscore(ts_mean(ts_backfill(ebitda/cap,120),60),subindustry)` TOP3000 d8 | 0.82 | 0.69 | 0.015 | ❌ |
| 基本面双 ratio 加和 | `add(...ebitda/cap..., ...cfo/cap...)` | 0.83 | 0.69 | 0.015 | ❌ |
| 纯价量反转家族 | `-rank(returns)` 等 | ≤1.0 | — | — | ❌ |

## 2. 早期错误的纠正

报告早期版本声称挖到 Sharpe **2.11**、9/9 检查全 PASS 的可提交 D0 因子。
**该结论错误**。两个独立根因：

1. **`simulate_many` 共享 session 跨线程并发**：轮询返回的 `alpha_id` 与其他在飞模拟串号，指标张冠李戴。已修复（per-task session + `code_match` 校验）。
2. **WQ 后端在并发轰炸下出现结果交错**：即使本地 code_match=True，后端可能短暂返回缓存中的别的 alpha 的指标；经 GC 后再拉取，真值稳定为 0.81/0.47 而非 2.11/2.27。

修复后**两次独立隔离单跑 + 双次拉取一致性核对**确认：
- `-rank(divide(ts_av_diff(close,5),ts_std_dev(close,20)))` 真实 SH **0.47**（曾报 2.11）
- `group_zscore(ts_mean(ts_backfill(ebitda/cap,120),60),subindustry)` 真实 SH **0.81**（曾报 2.27）

## 3. 推荐候选（如需提交，最强的有经济学意义因子）

**最强微结构 D0**（满足全部用户约束，但 SH 1.18 < 2.0）：

```
rank(ts_zscore(divide(volume, sharesout), 20))
delay=0, universe=TOP3000, neutralization=SUBINDUSTRY, decay=4, truncation=0.05
```

- 经济含义：**异常换手延续**。`volume/sharesout` 是日换手率，`ts_zscore(…,20)`
  量度其相对自身 20 日常态的偏离（含正则化），多偏离即关注度/流动性冲击，
  D0 短期延续。
- 正则化：`ts_zscore` + `rank` 双重。
- 非 IV：纯 PV 字段。
- 与已有因子相关性：账户 D0 因子皆为 IV/新闻/空头/基本面，本因子是纯换手微结构，
  经济轴正交，self-corr 期望低。
- 不通过 submit（SH 1.18 < 2.0）。

## 4. D0 提交门槛 2.0 的真实路径

账户里 SH 2.0+ 的现有 D0 因子（`LLRMo5Pv`、`d5QK2b3E`、`vRmkVOW3`、`E5kNGQxL`、
`GrkeWwx5`、`mLZkOw6x`、`0mz3J1AG`、`akN9pwQw`、`1Yo2OPjm` 等）分两类：

- **IV-based**（用户禁用）：`implied_volatility_*`、`pcr_oi_*` 系列。
- **多组件复杂加和**（非 IV，但不"简洁"）：4–6 个 `group_zscore` / `if_else(is_nan(...))` /
  `trade_when(news_pct_30min)` 项叠加（如 `blNEelXq` 加 4 项基本面，
  `GrkeWwx5` 加 3 项+新闻门控）。

要在非 IV 下到 2.0，需要走"多组件加和"路线，**与"简洁"要求冲突**。这是用户约束的硬边界。

## 5. 工具产出

- `scripts/wq_lib.py` — WQ 客户端，`simulate` 返回 `code_match`；废弃共享 session
- `scripts/measure_serial.py` — **严格串行 + code 核对**，唯一可信的测量器
- `scripts/isolated_verify.py` — 单跑 + 双次拉取一致性
- `scripts/check_submit.py` / `poll_selfcorr.py` — 不 submit 的提交检查
- 实测：本环境后台命令会**重复执行**，必须串行前台 + `code_match` 兜底

## 6. CLAUDE.md 已更新的关键事实

- delay=0 现已可模拟（旧"Delay 0 not available"已失效）
- D0 提交门槛：`LOW_SHARPE`=2.0、`LOW_FITNESS`=1.3、`SELF_CORRELATION`<0.7、
  `LOW_SUB_UNIVERSE_SHARPE`(~0.4)、`IS_LADDER_SHARPE`(0.5)、`CONCENTRATED_WEIGHT`
- 并发串号教训：必须 `code_match`，否则任何 Sharpe 都不可信
- 纯 PV D0 天花板 ~1.2 Sharpe；非 IV 简洁单信号也是
- `/correlations/prod` 403（账户无权限）；`/correlations/self` OK
