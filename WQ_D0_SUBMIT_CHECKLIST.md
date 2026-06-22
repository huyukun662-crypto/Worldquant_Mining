# WQ Brain D0 提交清单 — 可提交 + 低相关因子

> 账户:huyukun662@gmail.com · 仅 delay=0 · 全部已通过 **check submit**(8/8),
> 但**未实际 submit**(按用户约束:只确认可提交)。
> 相关性已证明到地板 ~0.48(由池中已提交非流动性因子 `88OgX1Jz` 驱动,
> 无法再降而仍保 SH>2)。

## 共用 Simulation Settings(A 与 C 完全相同)

| 字段 | 值 |
|---|---|
| Region | USA |
| Universe | TOP3000 |
| **Delay** | **0** |
| Neutralization | SUBINDUSTRY |
| Decay | 4 |
| Truncation | 0.08 |
| Pasteurization | ON |
| Unit Handling | VERIFY |
| NaN Handling | OFF |
| Language | FASTEXPR |

---

## 🥇 首选 A · Factor C(`O0pwMKog`)— Sharpe 最高

**Expression:**
```
add(add(add(-zscore(ts_decay_linear(ts_mean(divide(subtract(high, low), multiply(close, volume)), 750), 350)), -zscore(ts_decay_linear(ts_av_diff(close, 5), 5))), multiply(0.4, -zscore(ts_decay_linear(ts_av_diff(close, 20), 10)))), multiply(0.2, -zscore(ts_decay_linear(ts_mean(scl12_sentiment, 60), 40))))
```

| 指标 | 值 | 门槛 | 结果 |
|---|---|---|---|
| IS Sharpe | 2.09 | >2.0 | ✅ |
| Fitness | 3.10 | >1.3 | ✅ |
| Turnover | 0.103 | <0.7 | ✅ |
| Concentrated Weight | OK | <0.1 | ✅ |
| Sub-Universe Sharpe | OK | — | ✅ |
| **Self-Correlation** | **0.492** | <0.7 | ✅ |

**经济含义:** Amihud 非流动性(主引擎)+ 快/慢短期反转 + 社媒情绪过度反应。
冷门算子 `ts_av_diff`、`(high-low)/(close·volume)`,正则化 `zscore`+`ts_decay_linear`,无 IV 字段。

---

## 🥈 首选 B · Factor A(`88zq7z7m`)— 相关性最低

**Expression:**
```
add(add(-zscore(ts_decay_linear(ts_mean(divide(subtract(high, low), multiply(close, volume)), 750), 350)), -zscore(ts_decay_linear(ts_av_diff(close, 5), 5))), multiply(0.4, -zscore(ts_decay_linear(ts_av_diff(close, 20), 10))))
```

| 指标 | 值 | 门槛 | 结果 |
|---|---|---|---|
| IS Sharpe | 2.05 | >2.0 | ✅ |
| Fitness | ~2.9 | >1.3 | ✅ |
| Turnover | ~0.10 | <0.7 | ✅ |
| **Self-Correlation** | **0.485** | <0.7 | ✅ |

**与 C 区别:** 去掉情绪项,纯「非流动性 + 双周期反转」。相关性略低(0.485 vs 0.492)。

---

## 备选 · Factor B(`MPpA8aKo`)

**Expression:**
```
add(add(-zscore(ts_decay_linear(ts_mean(divide(subtract(high, low), multiply(close, volume)), 1000), 400)), -zscore(ts_decay_linear(ts_av_diff(close, 5), 5))), multiply(0.5, -zscore(ts_decay_linear(ts_av_diff(close, 15), 8))))
```
SH 2.05 · self_corr 0.483 · 非流动性窗口 1000(vs A/C 的 750)。

---

## 提交建议

1. **想要最高 Sharpe → 提交 Factor C**(2.09)。
2. **想要与已提交池最低相关 → 提交 Factor A**(0.485)。
3. A/B/C 三者互相高度相关(同为非流动性结构),**只提交其中一个**;不要同时提交两个以上,否则它们之间的 Self-Correlation 会互相顶到 >0.7。
4. 提交时 WQ 会异步跑 OS 检查(SHARPE / SELF_CORRELATION / IS_SHARPE),在当前竞赛 `IQC2026S1` 关闭前会停在 PENDING,属正常。
