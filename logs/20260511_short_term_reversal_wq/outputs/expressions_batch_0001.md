# Expression Batch 0001 - short_term_price_reversal

Mechanism: short_term_price_reversal | horizon: 1-10d | neutralization: INDUSTRY | delay: 1

## 1. `stm_rev_mean5`
```
rank(reverse(ts_mean(returns, 5)))
```
- Rationale: Long 5d losers. Pure short-term reversal baseline.
- Expected turnover direction: higher

## 2. `stm_rev_decay8`
```
rank(reverse(ts_decay_linear(returns, 8)))
```
- Rationale: Linear-decay-smoothed reversal; lower TO than mean5.
- Expected turnover direction: lower

## 3. `stm_rev_zscore10`
```
rank(reverse(ts_zscore(returns, 10)))
```
- Rationale: Z-scored reversal: normalizes by stock-specific vol.
- Expected turnover direction: neutral

## 4. `stm_rev_volcond`
```
rank(reverse(multiply(ts_mean(returns, 5), ts_mean(divide(volume, adv20), 5))))
```
- Rationale: Reversal weighted by abnormal volume - extreme moves on heavy flow tend to revert harder.
- Expected turnover direction: higher

## 5. `stm_rev_volnorm`
```
rank(reverse(divide(ts_delta(close, 3), ts_std_dev(returns, 20))))
```
- Rationale: Vol-normalized 3d price change; reversal in vol-adjusted space.
- Expected turnover direction: higher

## 6. `stm_rev_vwap`
```
rank(reverse(ts_decay_linear(divide(subtract(close, vwap), vwap), 5)))
```
- Rationale: Microstructure: close-vs-VWAP overextension; intraday traders fade.
- Expected turnover direction: higher

## 7. `stm_rev_tsrank10`
```
rank(reverse(ts_rank(returns, 10)))
```
- Rationale: Rank-based 10d reversal; more robust to return outliers than zscore.
- Expected turnover direction: neutral

## 8. `stm_rev_volwt_decay`
```
rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), s_log_1p(divide(volume, adv20))), 10)))
```
- Rationale: Z-scored reversal weighted by log(abnormal-volume), decay-smoothed - composite low-TO variant.
- Expected turnover direction: lower

