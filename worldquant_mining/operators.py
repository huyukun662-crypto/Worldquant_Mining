"""
Canonical WorldQuant Brain operator catalog.

Each entry mirrors the schema of the upstream `constants/operatorRAW.json`
(fetched from the WorldQuant Brain API):

    {
      "name": str,
      "category": str,           # Arithmetic | Logical | Time Series | Cross Sectional |
                                 # Group | Transformational | Vector | Reduce | Special
      "scope": list[str],        # subset of {COMBO, REGULAR, SELECTION, MATRIX, VECTOR}
      "definition": str,         # signature
      "description": str,        # short docstring
      "documentation": None,
      "level": "ALL" | None,
    }

The catalog covers operators publicly documented in the WorldQuant Brain
"Operators" reference page. The upstream miner's cached snapshot
(`constants/upstream_operatorRAW.json`) only contained 98 operators; this
file extends that to the full ~180 documented operators so the miner has
the complete search space.
"""

from __future__ import annotations

from typing import Dict, List

# Default scope for non-matrix scalar/cross-sectional operators
_DEF = ["COMBO", "REGULAR", "SELECTION"]
_TS = ["COMBO", "REGULAR", "SELECTION"]
_GRP = ["REGULAR", "SELECTION"]
_VEC = ["REGULAR"]


def _op(
    name: str,
    category: str,
    definition: str,
    description: str,
    scope: List[str] = None,
    level: str = "ALL",
) -> Dict:
    return {
        "name": name,
        "category": category,
        "scope": list(scope) if scope is not None else list(_DEF),
        "definition": definition,
        "description": description,
        "documentation": None,
        "level": level,
    }


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------
ARITHMETIC: List[Dict] = [
    _op("add", "Arithmetic", "add(x, y, filter=false), x + y",
        "Add all inputs (at least 2). If filter=true, replace NaN with 0 before adding."),
    _op("subtract", "Arithmetic", "subtract(x, y, filter=false), x - y",
        "Subtract y from x. If filter=true, NaN inputs treated as 0."),
    _op("multiply", "Arithmetic", "multiply(x, y, filter=false), x * y",
        "Multiply inputs (at least 2)."),
    _op("divide", "Arithmetic", "divide(x, y), x / y",
        "Divide x by y. NaN if y is 0 or NaN."),
    _op("inverse", "Arithmetic", "inverse(x), 1/x",
        "Reciprocal of x."),
    _op("reverse", "Arithmetic", "reverse(x), -x",
        "Negate x."),
    _op("sign", "Arithmetic", "sign(x)",
        "Sign of x: -1, 0, +1."),
    _op("abs", "Arithmetic", "abs(x)", "Absolute value of x."),
    _op("sqrt", "Arithmetic", "sqrt(x)", "Square root of x."),
    _op("power", "Arithmetic", "power(x, y), x ** y",
        "Raise x to the power of y."),
    _op("signed_power", "Arithmetic", "signed_power(x, y), sign(x) * abs(x)^y",
        "Preserves sign of x while raising magnitude to power y."),
    _op("log", "Arithmetic", "log(x)", "Natural logarithm of x."),
    _op("log10", "Arithmetic", "log10(x)", "Base-10 logarithm of x."),
    _op("log_diff", "Arithmetic", "log_diff(x), log(x) - log(ts_delay(x, 1))",
        "Log returns equivalent."),
    _op("s_log_1p", "Arithmetic", "s_log_1p(x), sign(x) * log(1 + abs(x))",
        "Signed log1p; tames magnitude while keeping sign."),
    _op("exp", "Arithmetic", "exp(x), e^x", "Natural exponential."),
    _op("max", "Arithmetic", "max(x, y, ...)",
        "Element-wise max across inputs (at least 2)."),
    _op("min", "Arithmetic", "min(x, y, ...)",
        "Element-wise min across inputs (at least 2)."),
    _op("ceiling", "Arithmetic", "ceiling(x)", "Smallest integer >= x."),
    _op("floor", "Arithmetic", "floor(x)", "Largest integer <= x."),
    _op("round", "Arithmetic", "round(x)", "Round to nearest integer."),
    _op("round_down", "Arithmetic", "round_down(x, f=1)",
        "Round x down to nearest multiple of f."),
    _op("fraction", "Arithmetic", "fraction(x), x - floor(x)",
        "Fractional part of x."),
    _op("mod", "Arithmetic", "mod(x, y), x % y", "Remainder of x divided by y."),
    _op("sin", "Arithmetic", "sin(x)", "Sine of x (radians)."),
    _op("cos", "Arithmetic", "cos(x)", "Cosine of x (radians)."),
    _op("tan", "Arithmetic", "tan(x)", "Tangent of x (radians)."),
    _op("arc_sin", "Arithmetic", "arc_sin(x)", "Inverse sine."),
    _op("arc_cos", "Arithmetic", "arc_cos(x)", "Inverse cosine."),
    _op("arc_tan", "Arithmetic", "arc_tan(x)", "Inverse tangent."),
    _op("tanh", "Arithmetic", "tanh(x)", "Hyperbolic tangent."),
    _op("densify", "Arithmetic", "densify(x)",
        "Convert sparse representation to dense; useful with group inputs."),
    _op("to_nan", "Arithmetic", "to_nan(x, value=0, reverse=false)",
        "Replace `value` with NaN, or NaN with `value` if reverse=true."),
    _op("nan_mask", "Arithmetic", "nan_mask(x, target)",
        "Set x to NaN wherever target is NaN."),
    _op("nan_out", "Arithmetic", "nan_out(x, lower=0, upper=0)",
        "Set x to NaN if it is outside [lower, upper]."),
    _op("purify", "Arithmetic", "purify(x)",
        "Replace +/-Inf with NaN."),
    _op("replace", "Arithmetic", "replace(x, target_list, new_list)",
        "Element-wise replacement of values in target_list with new_list."),
]


# ---------------------------------------------------------------------------
# Logical
# ---------------------------------------------------------------------------
LOGICAL: List[Dict] = [
    _op("and", "Logical", "and(x, y)", "Logical AND."),
    _op("or", "Logical", "or(x, y)", "Logical OR."),
    _op("not", "Logical", "not(x)", "Logical NOT."),
    _op("equal", "Logical", "equal(x, y), x == y", "Equality test."),
    _op("not_equal", "Logical", "not_equal(x, y), x != y", "Inequality test."),
    _op("less", "Logical", "less(x, y), x < y", "Strict less-than."),
    _op("less_equal", "Logical", "less_equal(x, y), x <= y", "Less-than-or-equal."),
    _op("greater", "Logical", "greater(x, y), x > y", "Strict greater-than."),
    _op("greater_equal", "Logical", "greater_equal(x, y), x >= y", "Greater-than-or-equal."),
    _op("is_nan", "Logical", "is_nan(x)", "True where x is NaN."),
    _op("is_not_nan", "Logical", "is_not_nan(x)", "True where x is not NaN."),
    _op("is_finite", "Logical", "is_finite(x)", "True where x is finite (not NaN, not +/-Inf)."),
    _op("if_else", "Logical", "if_else(cond, true_val, false_val)",
        "Return true_val where cond is true else false_val."),
]


# ---------------------------------------------------------------------------
# Time Series
# ---------------------------------------------------------------------------
TIME_SERIES: List[Dict] = [
    _op("ts_delay", "Time Series", "ts_delay(x, d)",
        "Value of x d days ago.", _TS),
    _op("ts_delta", "Time Series", "ts_delta(x, d), x - ts_delay(x, d)",
        "Change in x over the last d days.", _TS),
    _op("ts_sum", "Time Series", "ts_sum(x, d)",
        "Sum of x over the last d days.", _TS),
    _op("ts_product", "Time Series", "ts_product(x, d)",
        "Product of x over the last d days.", _TS),
    _op("ts_mean", "Time Series", "ts_mean(x, d)",
        "Arithmetic mean of x over the last d days.", _TS),
    _op("ts_median", "Time Series", "ts_median(x, d)",
        "Median of x over the last d days.", _TS),
    _op("ts_min", "Time Series", "ts_min(x, d)",
        "Minimum of x over the last d days.", _TS),
    _op("ts_max", "Time Series", "ts_max(x, d)",
        "Maximum of x over the last d days.", _TS),
    _op("ts_arg_min", "Time Series", "ts_arg_min(x, d)",
        "Index (0..d-1) of the min value of x in the last d days.", _TS),
    _op("ts_arg_max", "Time Series", "ts_arg_max(x, d)",
        "Index (0..d-1) of the max value of x in the last d days.", _TS),
    _op("ts_rank", "Time Series", "ts_rank(x, d)",
        "Time-series rank of x today within the last d days.", _TS),
    _op("ts_quantile", "Time Series", "ts_quantile(x, d, driver='gaussian')",
        "Quantile of x today vs last d days, returned in (0,1).", _TS),
    _op("ts_zscore", "Time Series", "ts_zscore(x, d), (x - ts_mean(x,d)) / ts_std_dev(x,d)",
        "Time-series z-score over a window of d days.", _TS),
    _op("ts_scale", "Time Series", "ts_scale(x, d, constant=0)",
        "Min-max rescale x to [0,1] over the last d days then add constant.", _TS),
    _op("ts_std_dev", "Time Series", "ts_std_dev(x, d)",
        "Population standard deviation of x over d days.", _TS),
    _op("ts_skewness", "Time Series", "ts_skewness(x, d)",
        "Skewness of x over the last d days.", _TS),
    _op("ts_kurtosis", "Time Series", "ts_kurtosis(x, d)",
        "Excess kurtosis of x over the last d days.", _TS),
    _op("ts_moment", "Time Series", "ts_moment(x, d, k)",
        "k-th central moment of x over d days.", _TS),
    _op("ts_count", "Time Series", "ts_count(x, d)",
        "Count of non-NaN values of x over the last d days.", _TS),
    _op("ts_count_nans", "Time Series", "ts_count_nans(x, d)",
        "Count of NaN values of x over the last d days.", _TS),
    _op("ts_corr", "Time Series", "ts_corr(x, y, d)",
        "Pearson correlation of x and y over the last d days.", _TS),
    _op("ts_covariance", "Time Series", "ts_covariance(x, y, d)",
        "Covariance of x and y over the last d days.", _TS),
    _op("ts_partial_corr", "Time Series", "ts_partial_corr(x, y, z, d)",
        "Partial correlation of x and y controlling for z, over d days.", _TS),
    _op("ts_co_skewness", "Time Series", "ts_co_skewness(x, y, d)",
        "Co-skewness of x with y over the last d days.", _TS),
    _op("ts_co_kurtosis", "Time Series", "ts_co_kurtosis(x, y, d)",
        "Co-kurtosis of x with y over the last d days.", _TS),
    _op("ts_regression", "Time Series", "ts_regression(y, x, d, lag=0, rettype=0)",
        "Time-series OLS regression of y on x over d days; rettype selects beta/alpha/resid/etc.", _TS),
    _op("ts_poly_regression", "Time Series", "ts_poly_regression(y, x, d, k=2, rettype=0)",
        "Polynomial regression of y on x of degree k over d days.", _TS),
    _op("ts_theilsen", "Time Series", "ts_theilsen(y, x, d)",
        "Theil-Sen robust slope estimator of y on x over d days.", _TS),
    _op("ts_decay_linear", "Time Series", "ts_decay_linear(x, d, dense=false)",
        "Linearly weighted moving average over d days (most recent gets highest weight).", _TS),
    _op("ts_decay_exp_window", "Time Series", "ts_decay_exp_window(x, d, factor=0.5, nan=true)",
        "Exponentially weighted moving average over d days.", _TS),
    _op("ts_weighted_decay", "Time Series", "ts_weighted_decay(x, k=0.5)",
        "Recursive weighted decay: y_t = k*x_t + (1-k)*y_{t-1}.", _TS),
    _op("ts_returns", "Time Series", "ts_returns(x, d, mode=1)",
        "Returns of x over d days; mode=1 simple, mode=2 log, mode=3 percent.", _TS),
    _op("ts_av_diff", "Time Series", "ts_av_diff(x, d), x - ts_mean(x, d)",
        "Deviation of x today from its d-day mean.", _TS),
    _op("ts_max_diff", "Time Series", "ts_max_diff(x, d), x - ts_max(x, d)",
        "Difference between current x and its d-day maximum.", _TS),
    _op("ts_min_diff", "Time Series", "ts_min_diff(x, d), x - ts_min(x, d)",
        "Difference between current x and its d-day minimum.", _TS),
    _op("ts_range", "Time Series", "ts_range(x, d), ts_max(x,d) - ts_min(x,d)",
        "Range of x over the last d days.", _TS),
    _op("ts_min_max_diff", "Time Series", "ts_min_max_diff(x, d, f=0.5)",
        "x - (f*ts_max + (1-f)*ts_min) over d days.", _TS),
    _op("ts_min_max_cps", "Time Series", "ts_min_max_cps(x, d, f=2.0)",
        "(ts_min(x,d) + ts_max(x,d)) - f*x.", _TS),
    _op("ts_percentage", "Time Series", "ts_percentage(x, d, percentage=0.5)",
        "Percentage value within the last d days.", _TS),
    _op("ts_ir", "Time Series", "ts_ir(x, d), ts_mean(x,d) / ts_std_dev(x,d)",
        "Information ratio over the last d days.", _TS),
    _op("ts_first", "Time Series", "ts_first(x, d)",
        "First non-NaN value of x in the last d days.", _TS),
    _op("ts_step", "Time Series", "ts_step(d), 1, 2, ..., d backwards",
        "Returns the day index (1..d).", _TS),
    _op("ts_backfill", "Time Series", "ts_backfill(x, lookback=5, k=1, ignore='NAN')",
        "Fill NaNs in x using the most recent non-NaN value within lookback.", _TS),
    _op("ts_target_tvr_decay", "Time Series", "ts_target_tvr_decay(x, target_tvr)",
        "Adaptive decay so that turnover targets `target_tvr`.", _TS),
    _op("ts_target_tvr_delta_limit", "Time Series", "ts_target_tvr_delta_limit(x, target_tvr)",
        "Limit per-step delta so realized turnover matches target.", _TS),
    _op("days_from_last_change", "Time Series", "days_from_last_change(x)",
        "Number of days since x last changed value.", _TS),
    _op("last_diff_value", "Time Series", "last_diff_value(x, d)",
        "Most recent value of x in last d days that differs from current.", _TS),
    _op("hump", "Time Series", "hump(x, hump=0.01)",
        "Apply turnover-reducing hump filter to x.", _TS),
    _op("jump_decay", "Time Series", "jump_decay(x, d, sensitivity=0.5, force=0.1)",
        "Decay x but allow jumps when relative change exceeds sensitivity.", _TS),
    _op("kth_element", "Time Series", "kth_element(x, d, k=1)",
        "k-th most recent non-NaN value of x within the last d days.", _TS),
    _op("inst_tvr", "Time Series", "inst_tvr(x, d)",
        "Instantaneous turnover of x over the last d days.", _TS),
    _op("ts_weighted_mean", "Time Series", "ts_weighted_mean(x, w, d)",
        "Weighted mean of x with weights w over the last d days.", _TS),
    _op("ts_entropy", "Time Series", "ts_entropy(x, d, buckets=10)",
        "Shannon entropy of x's distribution over the last d days.", _TS),
]


# ---------------------------------------------------------------------------
# Cross Sectional
# ---------------------------------------------------------------------------
CROSS_SECTIONAL: List[Dict] = [
    _op("rank", "Cross Sectional", "rank(x, rate=2)",
        "Cross-sectional rank of x in (0,1)."),
    _op("zscore", "Cross Sectional", "zscore(x)",
        "Cross-sectional z-score of x."),
    _op("normalize", "Cross Sectional", "normalize(x, useStd=false, limit=0.0)",
        "Demean x cross-sectionally; optionally divide by std and clip to limit."),
    _op("scale", "Cross Sectional", "scale(x, scale=1, longscale=1, shortscale=1)",
        "Scale x so that sum of absolute values equals scale."),
    _op("scale_down", "Cross Sectional", "scale_down(x, constant=0)",
        "Scale x to [0,1] cross-sectionally then add constant."),
    _op("quantile", "Cross Sectional", "quantile(x, driver='gaussian', sigma=1.0)",
        "Map x to a target distribution (gaussian/uniform/cauchy) cross-sectionally."),
    _op("winsorize", "Cross Sectional", "winsorize(x, std=4)",
        "Clip x to +/- std standard deviations cross-sectionally."),
    _op("vector_neut", "Cross Sectional", "vector_neut(x, y)",
        "Project x onto the orthogonal complement of y cross-sectionally."),
    _op("regression_neut", "Cross Sectional", "regression_neut(y, x)",
        "Cross-sectional residual of regressing y on x."),
    _op("regression_proj", "Cross Sectional", "regression_proj(y, x)",
        "Cross-sectional projection of y onto x."),
    _op("one_side", "Cross Sectional", "one_side(x, side='long')",
        "Keep only positive (long) or negative (short) values; zero out the other side."),
    _op("right_tail", "Cross Sectional", "right_tail(x, maximum=0)",
        "Keep values <= maximum, set the rest to NaN."),
    _op("left_tail", "Cross Sectional", "left_tail(x, minimum=0)",
        "Keep values >= minimum, set the rest to NaN."),
    _op("truncate", "Cross Sectional", "truncate(x, maxPercent=0.01)",
        "Cap absolute weight of any single asset to maxPercent of book."),
]


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------
GROUP: List[Dict] = [
    _op("group_rank", "Group", "group_rank(x, group)",
        "Cross-sectional rank of x within each group.", _GRP),
    _op("group_zscore", "Group", "group_zscore(x, group)",
        "Z-score of x within each group.", _GRP),
    _op("group_normalize", "Group", "group_normalize(x, group, useStd=false, limit=0.0)",
        "Normalize x within each group.", _GRP),
    _op("group_scale", "Group", "group_scale(x, group)",
        "Scale x to [0,1] within each group.", _GRP),
    _op("group_mean", "Group", "group_mean(x, weight, group)",
        "Mean of x within each group.", _GRP),
    _op("group_median", "Group", "group_median(x, group)",
        "Median of x within each group.", _GRP),
    _op("group_min", "Group", "group_min(x, group)",
        "Minimum of x within each group.", _GRP),
    _op("group_max", "Group", "group_max(x, group)",
        "Maximum of x within each group.", _GRP),
    _op("group_sum", "Group", "group_sum(x, group)",
        "Sum of x within each group.", _GRP),
    _op("group_std_dev", "Group", "group_std_dev(x, group)",
        "Standard deviation of x within each group.", _GRP),
    _op("group_count", "Group", "group_count(x, group)",
        "Number of non-NaN values of x within each group.", _GRP),
    _op("group_percentage", "Group", "group_percentage(x, group, percentage=0.5)",
        "Percentile value of x within each group.", _GRP),
    _op("group_neutralize", "Group", "group_neutralize(x, group)",
        "Subtract within-group mean from x.", _GRP),
    _op("group_vector_neut", "Group", "group_vector_neut(x, y, group)",
        "Project x onto orthogonal complement of y within each group.", _GRP),
    _op("group_backfill", "Group", "group_backfill(x, group, d, std=4.0)",
        "Backfill NaNs of x using non-NaN values of the same group within d days.", _GRP),
    _op("group_cartesian_product", "Group", "group_cartesian_product(group1, group2)",
        "Cartesian product of two group factors."),
    _op("group_corr", "Group", "group_corr(x, y, group)",
        "Pearson correlation of x and y within each group.", _GRP),
    _op("combo_a", "Group", "combo_a(x, y, ...)",
        "Combine two or more alpha vectors with adaptive weighting."),
]


# ---------------------------------------------------------------------------
# Transformational
# ---------------------------------------------------------------------------
TRANSFORMATIONAL: List[Dict] = [
    _op("bucket", "Transformational",
        "bucket(rank(x), range='0,1,0.1' | buckets='2,5,6,7,10' | skipBegin=false)",
        "Bucket x into discrete bins by range or explicit buckets."),
    _op("trade_when", "Transformational", "trade_when(condition, alpha, exit_condition)",
        "Take alpha exposure only when condition is true; flatten when exit_condition is true."),
    _op("generate_stats", "Transformational", "generate_stats(x)",
        "Emit basic statistics about x for diagnostics."),
    _op("filter", "Transformational", "filter(x, h=2 ** -0.001, t='days', d=1)",
        "Apply a smoothing/filtering transform to x."),
    _op("pasteurize", "Transformational", "pasteurize(x)",
        "Set x to NaN where the entire universe row is NaN; common preprocessing step."),
    _op("clamp", "Transformational", "clamp(x, lower=0, upper=0, inverse=false, mask='NAN')",
        "Clip x to [lower, upper] range; optionally invert the mask."),
    _op("coalesce", "Transformational", "coalesce(x1, x2, ...)",
        "Take the first non-NaN value across the inputs (cell-by-cell)."),
    _op("convert_dt", "Transformational", "convert_dt(x, target='date')",
        "Convert datetime-typed field x to a target representation."),
]


# ---------------------------------------------------------------------------
# Vector
# ---------------------------------------------------------------------------
VECTOR: List[Dict] = [
    _op("vec_avg", "Vector", "vec_avg(x)",
        "Average of vector-typed field x.", _VEC),
    _op("vec_sum", "Vector", "vec_sum(x)",
        "Sum of vector-typed field x.", _VEC),
    _op("vec_max", "Vector", "vec_max(x)",
        "Max element of vector-typed field x.", _VEC),
    _op("vec_min", "Vector", "vec_min(x)",
        "Min element of vector-typed field x.", _VEC),
    _op("vec_count", "Vector", "vec_count(x)",
        "Number of non-NaN elements in vector-typed field x.", _VEC),
    _op("vec_choose", "Vector", "vec_choose(x, nth=0)",
        "Pick the nth element of vector-typed field x.", _VEC),
    _op("vec_ir", "Vector", "vec_ir(x), vec_avg(x)/vec_stddev(x)",
        "Information ratio across the vector field.", _VEC),
    _op("vec_norm", "Vector", "vec_norm(x)",
        "L2 norm across the vector field.", _VEC),
    _op("vec_powersum", "Vector", "vec_powersum(x, p=2)",
        "Sum of x_i^p across the vector field.", _VEC),
    _op("vec_range", "Vector", "vec_range(x), vec_max(x) - vec_min(x)",
        "Range across the vector field.", _VEC),
    _op("vec_skewness", "Vector", "vec_skewness(x)",
        "Skewness across the vector field.", _VEC),
    _op("vec_kurtosis", "Vector", "vec_kurtosis(x)",
        "Excess kurtosis across the vector field.", _VEC),
    _op("vec_stddev", "Vector", "vec_stddev(x)",
        "Standard deviation across the vector field.", _VEC),
    _op("vec_percentage", "Vector", "vec_percentage(x, percentage=0.5)",
        "Percentile value across the vector field.", _VEC),
]


# ---------------------------------------------------------------------------
# Reduce  (event/list aggregations)
# ---------------------------------------------------------------------------
REDUCE: List[Dict] = [
    _op("reduce_sum", "Reduce", "reduce_sum(x)", "Sum across the reduce axis."),
    _op("reduce_avg", "Reduce", "reduce_avg(x)", "Mean across the reduce axis."),
    _op("reduce_min", "Reduce", "reduce_min(x)", "Min across the reduce axis."),
    _op("reduce_max", "Reduce", "reduce_max(x)", "Max across the reduce axis."),
    _op("reduce_range", "Reduce", "reduce_range(x), reduce_max(x) - reduce_min(x)",
        "Range across the reduce axis."),
    _op("reduce_count", "Reduce", "reduce_count(x)",
        "Count of non-NaN entries across the reduce axis."),
    _op("reduce_stddev", "Reduce", "reduce_stddev(x)",
        "Standard deviation across the reduce axis."),
    _op("reduce_skewness", "Reduce", "reduce_skewness(x)",
        "Skewness across the reduce axis."),
    _op("reduce_kurtosis", "Reduce", "reduce_kurtosis(x)",
        "Excess kurtosis across the reduce axis."),
    _op("reduce_ir", "Reduce", "reduce_ir(x)",
        "Information ratio across the reduce axis."),
    _op("reduce_norm", "Reduce", "reduce_norm(x)",
        "L2 norm across the reduce axis."),
    _op("reduce_percentage", "Reduce", "reduce_percentage(x, percentage=0.5)",
        "Percentile value across the reduce axis."),
    _op("reduce_powersum", "Reduce", "reduce_powersum(x, p=2)",
        "Sum of x_i^p across the reduce axis."),
    _op("reduce_choose", "Reduce", "reduce_choose(x, nth=0)",
        "Pick the nth element across the reduce axis."),
]


# ---------------------------------------------------------------------------
# Special
# ---------------------------------------------------------------------------
SPECIAL: List[Dict] = [
    _op("in", "Special", "in(x, list)", "True if x is in `list`."),
    _op("self_corr", "Special", "self_corr(x, d)",
        "Correlation of x with its own past over d days."),
    _op("universe_size", "Special", "universe_size()",
        "Number of instruments in the active universe."),
    _op("size_of", "Special", "size_of(group)",
        "Number of instruments in each group."),
    _op("is_alpha_universe", "Special", "is_alpha_universe(x)",
        "True if instrument is in the current alpha universe."),
]


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------
CANONICAL_OPERATORS: List[Dict] = (
    ARITHMETIC
    + LOGICAL
    + TIME_SERIES
    + CROSS_SECTIONAL
    + GROUP
    + TRANSFORMATIONAL
    + VECTOR
    + REDUCE
    + SPECIAL
)


def operators_by_category() -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for op in CANONICAL_OPERATORS:
        out.setdefault(op["category"], []).append(op)
    return out


def operator_names() -> List[str]:
    return [op["name"] for op in CANONICAL_OPERATORS]
