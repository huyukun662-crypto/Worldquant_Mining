# D1 非 TOP3000 universe 挖掘findings

按"换 universe、不要 TOP3000"方向,系统扫了本账号 USA 可用的所有 universe
(batch22–24,~24 次回测)。

## 账号可用 universe(USA, delay=1)

| universe | 可用? | 说明 |
|---|:---:|---|
| TOP3000 | ✅ | 用户要求规避 |
| **TOP1000** | ✅ | **winner 所在(已可提交)** |
| TOP500 | ✅ | 反转 fitness 顶在 ~0.90 |
| TOP200 | ✅ | 太窄,SH≈0.75 |
| TOPSP500 (S&P500) | ✅ | 反转 fitness 顶在 ~0.89 |
| TOPDIV3000 | ❌ | "not available for EQUITY/USA" |
| MINVOL1M | ❌ | "not available for EQUITY/USA" |

## 反转配方在各 universe 的最优(rank(-ts_rank(returns,N)))

| universe | 最优配置 | SH | TO | Fitness | 可提交 |
|---|---|:---:|:---:|:---:|:---:|
| **TOP1000** | returns-5, decay16 | 2.14 | 0.62 | **1.01** | ✅ |
| TOPSP500 | returns-10, decay24 | 1.79 | 0.50 | 0.89 | ❌ |
| TOP500 | returns-10, decay24 | 1.73 | 0.52 | 0.90 | ❌ |
| TOP200 | returns-5, decay16 | 0.75 | 0.61 | 0.25 | ❌ |

## 关键结论

1. **现有 winner 已满足"非 TOP3000"**:`rank(-ts_rank(returns,5))` 跑在
   **TOP1000**(不是 TOP3000),8 项 submit 检查全 PASS。
2. **更小的 universe(TOP500/TOPSP500)过不了 fitness**:反转 SH 很高
   (1.73–1.79)但年化收益偏低(大盘股反转弱),Fitness 顶在 0.89–0.90。
3. **truncation 在这些 universe 上完全无效**:0.08 / 0.12 / 0.15 / 0.20 下
   TOPSP500 returns-10 的 SH/TO/FIT 一模一样(1.79 / 0.50 / 0.89)——
   rank 信号在 500 只票上已充分分散,权重从不触及 truncation 上限。
4. **TOP200 太窄**:票池太小,L/S 组合 Sharpe 掉到 0.75。

→ 在"简洁单表达式 D1"约束下,**唯一能让反转过 submit 的非 TOP3000 universe
就是 TOP1000**(= 现有 winner)。TOP500/TOPSP500 差最后约 0.10 的 fitness,
TOP200 差太远。

## 复现
```bash
python scripts/run_batch22.py   # universe 发现
python scripts/run_batch23.py   # TOPSP500/TOP500 反转调参
python scripts/run_batch24.py   # truncation 扫描(确认无效)
```
