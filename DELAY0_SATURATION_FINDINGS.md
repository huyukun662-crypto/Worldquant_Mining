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

---

## 补充:alphaCount 拥挤代理 + 高价值模块实测(用户截图方向)

WQ 数据卡的 "Value score"(高=信息量大/不拥挤)指向 Model(7)、Sentiment(7)。
实测 delay-0:

### 1. Model / Sentiment 在 delay-0 根本不存在
delay-0 TOP3000 只有 13 个 dataset、7 个类别:Analyst, Earnings, Fundamental,
News, Option, Price Volume, Social Media。**Model 和 Sentiment 是 delay-1 专属。**

### 2. 每个字段带 alphaCount —— 这就是本地可测的"拥挤代理"
| 字段/数据集 | alphaCount(拥挤) | 备注 |
|---|---|---|
| close / returns / volume (pv1) | 5095 / 3040 / 2978 | 挖烂 |
| fundamental6 | 10,624 | 挖烂 |
| **option8 波动率(用户IV-skew在此)** | **5,088** | 用户池子所在,拥挤 |
| implied_volatility_call_180 / put_180 | 433 / 352 | 中度拥挤 |
| **option6 预测波动率(131字段)** | **≈0** | 几乎无人用 |
| pv13 关系数据 | 18-105 | 冷门 |

→ 解释了减分:用户池子在 option8(5088 alphas)的拥挤偏度上,再加相关因子边际为负。

### 3. 冷门高价值数据实测:全部无 edge
- **option6 预测波动率(alphaCount≈0)**:vol-of-vol / VRP / 期限结构 / skew曲率 /
  gamma成本 等 10 个简单构造 → |fitness| < 0.4。
- **option6 × 偏度组合**(skew/预测波动、skew|高vol-of-vol、skew⊥vol):fitness 从
  raw skew 的 4.65 **暴跌到 1.1-1.75**,全部跌破 2.5。冷门字段稀释 edge。
- **pv13 供应链动量**(竞争对手/客户/合作方收益,alphaCount 18-105):|fitness|<0.4。

## 终极结论(铁证)
**在 delay-0 此账户层级,edge 与拥挤完全混杂、不可分离:**
- 唯一有 edge 的信号 = call-put 偏度(option8,alphaCount 5088,拥挤)。
- 每个不拥挤字段(option6 alphaCount≈0、pv13 18-105)都**没有 edge**。
- 任何让偏度去相关的改造都把 fitness 砍到 2.5 以下。

→ 想"加分"需要"高 edge ∧ 低拥挤"同时成立,而这在 delay-0 此层级**不可能**。
**它只可能在 delay-1 成立**:那里 Model(value 7)/Sentiment(value 7)等高价值
数据存在,且 alphaCount 代理可同样用于预筛低拥挤字段。delay-1 是唯一出路。
