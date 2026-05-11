# Expression Batch 0001 - short_term_price_reversal

Mechanism: short_term_price_reversal | horizon: 1-10d | neutralization: INDUSTRY | delay: 1

## 1. `r2_volwt_decay20`
```
rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 20)))
```
- Rationale: Round-1 seed with decay 10 -> 20. Direct TO refinement of the closest miss.
- Expected turnover direction: lower

## 2. `r2_zscore10_decay16`
```
rank(reverse(ts_decay_linear(ts_zscore(returns, 10), 16)))
```
- Rationale: Pure z-score reversal with decay-16 smoothing (R1 zscore10 had SH 1.97 / TO 0.69).
- Expected turnover direction: lower

## 3. `r2_tsrank10_decay16`
```
rank(reverse(ts_decay_linear(ts_rank(returns, 10), 16)))
```
- Rationale: Rank-based reversal with decay-16 smoothing (R1 tsrank10 had SH 1.95 / TO 0.69).
- Expected turnover direction: lower

## 4. `r2_volwt_decay30`
```
rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 30)))
```
- Rationale: Same composite as #1 but decay 30 - aggressive TO suppression at the cost of some SH.
- Expected turnover direction: lower

## 5. `r2_vwap_decay20`
```
rank(reverse(ts_decay_linear(divide(subtract(close, vwap), vwap), 20)))
```
- Rationale: Close-VWAP fade smoothed over 20d (R1 vwap with decay 5 was SH 1.20 / TO 0.33).
- Expected turnover direction: lower

## 6. `r2_volnorm_decay16`
```
rank(reverse(ts_decay_linear(divide(ts_delta(close, 5), ts_std_dev(returns, 20)), 16)))
```
- Rationale: Vol-normalized 5d price change, decay-16 (R1 volnorm 3d/decay-0 was SH 1.33 / TO 0.40).
- Expected turnover direction: lower

## 7. `r2_zscore10_volwt_decay20`
```
rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 10), log(add(divide(volume, adv20), 1))), 20)))
```
- Rationale: Seed but with longer 10d z-score horizon; captures more reversal mass.
- Expected turnover direction: lower

## 8. `r2_volnorm_zscore_decay20`
```
rank(reverse(ts_decay_linear(ts_zscore(divide(ts_delta(close, 3), ts_std_dev(returns, 20)), 5), 20)))
```
- Rationale: Vol-normalized 3d delta z-scored then decay-20 smoothed - double-normalization composite.
- Expected turnover direction: lower

