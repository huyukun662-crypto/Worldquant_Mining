# A 股因子挖掘方法与逻辑

## 1. 方法边界

该流程只面向 A 股，因此 `region` 固定为 `CHN`。用户通过 `--universe` 选择全 A、
沪深两市主要宽基指数或科创/创业板指数；delay、中性化方式和 decay 分别由
`--delay`、`--neutralization`、`--decay` 指定。算法不从
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

一次实验只使用用户指定的一个股票池，避免把不同范围的表现混在一起。搜索目标
是 Brain 返回的 IS Sharpe；换手率不低于 0.25 的试验施加惩罚。

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
python -m mining_pipeline.wq_pipeline --universe CSI300 --n-exprs 20 \
  --delay 1 --neutralization INDUSTRY --decay 8 \
  --seed 20260726 --dry-run \
  --out CHN_FACTOR_CANDIDATES.json

# 有 credential.txt 且安装 optuna 后运行权威搜索
python -m mining_pipeline.wq_pipeline --universe CSI300 --n-exprs 5 --trials 8 \
  --delay 1 --neutralization INDUSTRY --decay 8 \
  --out CHN_WQ_MINING_REPORT.json
```

重复传入 `--neutralization` 可以只在用户选择的若干中性化方式之间搜索，例如
`--neutralization INDUSTRY --neutralization MARKET`。不传 `--neutralization` 或
`--decay` 时，程序才使用该区域的完整中性化列表或默认 decay 搜索空间。

可选股票池代码：

| 代码 | 范围 |
|---|---|
| `ALL_A` | 全部 A 股 |
| `SSE_COMPOSITE` | 上证综指 |
| `SSE50` | 上证 50 |
| `CSI_A500` | 中证 A500 |
| `CSI300` | 沪深 300 |
| `CSI500` | 中证 500 |
| `CSI800` | 中证 800 |
| `CSI1000` | 中证 1000 |
| `CSI2000` | 中证 2000 |
| `SZSE_COMPONENT` | 深证成指 |
| `SZSE100` | 深证 100 |
| `CHINEXT` | 创业板指 |
| `STAR50` | 科创 50 |

命令行也接受中文别名 `--universe 上证指数`（或 `上证综指`）和
`--universe 深证成指`；写入报告和提交设置时会分别规范化为
`SSE_COMPOSITE` 与 `SZSE_COMPONENT`。
