# D0 因子挖掘报告（含方法学更正）

账户：`2445560398@qq.com` ｜ 区域：USA ｜ 仅 **delay = 0**

## 0. 重要更正（先说结论）

本报告的早期版本声称挖到一个 Sharpe **2.11**、9 项提交检查全 PASS 的 D0
因子。**该结论是错误的，源于一个测量 bug**，已在此版更正。

- **根因**：`scripts/wq_lib.py` 的 `simulate_many()` 用线程池**共享同一个
  `requests.Session`** 并发提交模拟。并发下轮询返回的 `alpha_id` 会与其他在飞
  模拟**串号**，导致指标被张冠李戴（某表达式拿到了别的 alpha 的 Sharpe）。
- **复现/证实**：用隔离单跑 + **核对返回 alpha 的 `regular.code` 是否等于提交
  的表达式**（`code_match`），对同一表达式 `-rank(divide(ts_av_diff(close,5),
  ts_std_dev(close,20)))` 跑了两次独立单跑（alpha `vRm6Xjvv`、`vRm6mb1A`，均
  `code_match=True`），真实结果都是 **Sharpe 0.47 / Fitness 0.14 → FAIL**。
- **修复**：`simulate_many` 已弃用共享 session（改为每任务独立 session +
  `code_match` 校验）；`simulate()` 现在返回 `code_match`；新增
  `scripts/measure_serial.py`（严格串行 + code 核对）与
  `scripts/isolated_verify.py`（隔离单跑）。

> 教训：**任何 WQ 指标在采信前必须确认该 alpha 的 `regular.code` 等于你提交的
> 表达式**，尤其是并发/限流环境下。

## 1. 经 code 核对的真实结果（纯价量 D0 天花板）

严格串行 + `code_match=True` 测得的纯价量 D0 信号真实强度：

| 表达式（经济含义） | Sharpe | Turnover | 能否提交 |
|---|---|---|---|
| `-rank(returns)` （1 日反转，最强） | ~1.7 | >0.7 | ❌ TO 超限 + SH<2.0 |
| `-rank(ts_mean(abs(returns)/(volume*vwap),20))`（Amihud 非流动性） | ~1.0 | 0.35 | ❌ SH<2.0 |
| `rank(ts_av_diff((high-low)/close,10))`（日内振幅） | ~1.0（符号不稳） | 0.25 | ❌ |
| `-ts_zscore(close,5)`（反转） | ~0.95 | 0.51 | ❌ |
| `-rank(ts_av_diff(close,5)/ts_std_dev(close,20))`（波动率归一化反转） | **0.47** | 0.53 | ❌ |

**结论：纯价量 D0 因子的真实 Sharpe 天花板约 1.7，无一能达到 D0 提交门槛
（Sharpe>2.0、Fitness>1.3）。** 这与账户已有的 D0 可提交因子全部依赖更丰富数据
（IV / 新闻 / 空头持仓 / 基本面 group_zscore）相吻合——纯 PV 不足以越过 D0 的 2.0 线。

## 2. 仍然有效的成果

- **D0 提交门槛实测**（来自 `GET /alphas/{id}/check`）：`LOW_SHARPE` limit
  **2.0**（非 d1 的 1.25）、`LOW_FITNESS` **1.3**，外加 `LOW_SUB_UNIVERSE_SHARPE`、
  `IS_LADDER_SHARPE`(0.5)、`CONCENTRATED_WEIGHT`、`SELF_CORRELATION`(<0.7)。
- **不 submit 的 pre-submit 校验**可行：`GET /alphas/{id}/check` +
  `GET /alphas/{id}/correlations/self`（`/correlations/prod` 在本账户 403）。
  工具：`scripts/check_submit.py`。
- **delay=0 现已可模拟**（旧 CLAUDE.md 的 "Delay 0 not available" 已失效）。
- 账户已提交的 D0 因子经济轴为 IV/新闻/空头/基本面；任何纯价量新因子与其
  天然低相关——“与以前不相关”这一点容易满足，难点在 Sharpe。

## 3. 工具

```bash
# 严格串行 + code 核对的 D0 测量（推荐，唯一可信）
python scripts/measure_serial.py jobs.json out.json

# 隔离单跑一个表达式（带 code_match）
python scripts/isolated_verify.py "EXPR" TOP500 4 0.05 SUBINDUSTRY

# 不 submit 的提交检查
python scripts/check_submit.py <alpha_id>
```

> ⚠️ 本执行环境会**重叠/重复执行后台命令**，多个实例并发打 API 会再次引入
> 串号与文件覆盖。务必：单实例、串行、前台执行关键测量，并以 `code_match` 把关。

## 4. 下一步（待用户定方向）

纯价量到不了 D0 的 2.0 线。要真正挖出可提交的 D0 因子，需引入**非 IV 的更丰富
数据**。推荐路径：基于**基本面**做 D0 因子（如 `group_zscore(quantile(<价值/质量
比率>))` 形态，但用与账户现有因子不同的比率，确保 self-corr<0.7），这类信号在
D0 上换手低、横截面 Sharpe 可观，是账户已验证能过 2.0 的形态。
