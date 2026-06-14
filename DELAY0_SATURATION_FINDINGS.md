# delay-0 因子挖掘饱和结论 (账户 2445560398@qq.com)

## 起点
用户在 WQ 已提交 3 个 delay-0 IV-skew alpha(QPEXXXaQ=60d, O0oEYx97/j21EEbx9=180d
call-put 偏度),delay-0 Score ≈ 12,166。目标:再加 1 个能**提升** Score 的因子。

## 核心发现:每个新 delay-0 因子都减分,根因是"生产池拥挤度"
两个候选都做了 Performance Comparison,都**减分**:
- RRrwQYl0(efficiency+PV,对自有池 corr 0.21,fitness 1.70)→ -188
- Vk8b8ZVG(30d 偏度,fitness 4.65 远超池均值,自相关 0.55)→ 仍减分

fitness 4.65 远高于池子却仍减分 → 排除"质量稀释",指向**对全平台生产池的相关度**
(call-put 偏度、价量反转是被全社区挖烂的教科书信号)。

## 为什么本地无法解决(账户层级墙)
| 想做 | 状态 |
|---|---|
| 测 `/correlations/prod`(真正绑定约束) | ❌ HTTP 403,层级不够 |
| 横截面去拥挤 `regression_neut` | ❌ "inaccessible operator",被封 |
| `vector_neut(skew30⊥skew180)` 残差化 | ✅ 可用,但 maxCorr 仍 0.55(碰不到 60d 重叠),无效 |
| `tanh` | ❌ 被封 |

## 系统性扫描结论(约 19 批,130+ 次 WQ 模拟)
- **有 edge 的信号**只在 IV 偏度族(fitness 3-5),但全是教科书信号 → 生产池高相关 → 减分。
  - tenor 扫描:30d fit4.96 / 90d 4.65 / 120d 4.68,但都与池子 60/180d 高相关。
- **慢速正交信号**(动量/低波/价值/质量/短做空)→ delay-0 上 SH≈0,无 edge。
- **非线性/残差化**:可用的单调变换(signed_power fit2.42)不改变 PnL 形状,不去相关;
  能去相关的算子被封。
- **新闻事件微结构**(news_pct_*, max_up/dn_ret, open_gap, news_ls 等 38 个反应字段)
  → 全部 fitness < 0.2,换手 0.17-0.25,又噪又快,无 edge。

## 结论
**delay-0 在此账户层级已饱和。** 用户的 3 个 IV-skew alpha 已占据该层级可达的
"非拥挤 edge";再加任何因子,要么复制拥挤的偏度信号(经生产池相关而减分),
要么本身无 edge。本地既测不到拥挤度(403)、也改不动(去拥挤算子被封)。

## 真正的出路(需账户层级或赛场变更)
1. **升级账户层级** —— 解锁 `/correlations/prod`(直接测拥挤)+ `regression_neut`
   (直接去拥挤)+ 更多 delay-0 数据。唯一从根上解锁的途径。
2. **转 delay-1** —— 解锁 378 分析师 + 58 情绪等未拥挤数据,且 regression_neut/
   prod-corr 往往可用;独立 delay-1 评分桶。
3. **承认饱和,停止再加 delay-0。**
