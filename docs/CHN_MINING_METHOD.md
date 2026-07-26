# A 股因子挖掘方法与逻辑

## 1. 目标与边界

挖掘对象是 WorldQuant Brain 的 `CHN / TOP2000U / delay=1` 股票池。流程不从
Alpha101 或仓库的经典因子模板复制表达式，而是重新组合价量字段、时序算子和
截面标准化算子。候选表达式不是因子结论；只有 Brain `/simulations` 返回的结果
才是最终评价依据。

## 2. 候选生成

生成器从价格、成交量、VWAP、收益率、市值和流动性字段中抽样，再组合：

1. **时序变换**：均值、波动率、变化量、相关性、时序排名、衰减；
2. **关系构造**：加减乘除，用于表达价量、价格—流动性或风险—收益关系；
3. **截面处理**：`rank`、`zscore`、`scale`、`normalize`，形成可比较的股票排序信号；
4. **窗口参数**：初始窗口来自 3/5/10/20/40/60 日，正式搜索时由 Optuna 在
   3–60 日内重新选择。

固定随机种子只用于保证实验可复现，不代表固定模板。

## 3. 结构预筛选

随机语法树会产生大量没有经济含义的表达式，因此在付费/限流的 Brain 仿真前，
候选必须同时满足：

- 至少使用两个不同的数据字段；
- 至少包含一个时序算子和一个可优化窗口；
- 排除 `divide(x, x)`、`subtract(x, x)` 等恒等或恒零结构；
- 对表达式去重。

这一步只衡量“是否值得测试”，不预测收益，也不会生成虚假的 Sharpe。

## 4. 联合参数搜索

对通过结构筛选的每个表达式，TPE 搜索同时调整：

- 表达式回看窗口；
- decay、truncation、pasteurization；
- A 股可用的行业/子行业/板块、动量反转、拥挤度、快慢风格等中性化方式。

股票池固定为 `TOP2000U`，避免把不同股票池的表现混在一次实验中。搜索目标是
Brain 返回的 IS Sharpe；换手率不低于 0.25 的试验施加惩罚。

## 5. 评价与防止过拟合

建议按以下顺序判断：

1. Brain IS Sharpe > 1.25；
2. Brain IS turnover < 0.25；
3. 检查 fitness、drawdown、持仓数量及平台 checks；
4. OS 数据可用时要求 OS Sharpe 不低于 IS Sharpe；
5. 对幸存因子做表达式相似度和收益相关性去重，只保留不同经济逻辑的信号。

Dry-run JSON 中的 `UNEVALUATED` 只表示候选已生成，不能称为有效因子。

## 6. 执行

```bash
# 生成并解释候选，不访问 Brain
python -m mining_pipeline.wq_pipeline --region CHN --n-exprs 20 \
  --seed 20260726 --dry-run --out CHN_FACTOR_CANDIDATES.json

# 有 credential.txt 且安装 optuna 后运行权威搜索
python -m mining_pipeline.wq_pipeline --region CHN --n-exprs 5 --trials 8 \
  --out CHN_WQ_MINING_REPORT.json
```
