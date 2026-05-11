# Expression Batch 0001 - short_term_price_reversal

Mechanism: short_term_price_reversal | horizon: 1-10d | neutralization: INDUSTRY | delay: 1

## 1. `mom_mean60`
```
rank(ts_mean(returns, 60))
```
- Rationale: Pure 60d momentum baseline; long the residual winners.
- Expected turnover direction: lower

## 2. `mom_decay60`
```
rank(ts_decay_linear(returns, 60))
```
- Rationale: Linear-decay-smoothed 60d momentum; smoother weighting toward recent.
- Expected turnover direction: lower

## 3. `mom_sharpe60`
```
rank(divide(ts_mean(returns, 60), ts_std_dev(returns, 60)))
```
- Rationale: Risk-adjusted (Sharpe-like) 60d momentum - normalizes by realized vol.
- Expected turnover direction: lower

## 4. `mom_mean40`
```
rank(ts_mean(returns, 40))
```
- Rationale: Shorter 40d horizon; tests where the medium-term effect peaks.
- Expected turnover direction: neutral

## 5. `mom_pricez60`
```
rank(divide(subtract(close, ts_mean(close, 60)), ts_std_dev(close, 60)))
```
- Rationale: Price-level z-score over 60d - close-vs-60d-mean normalized by 60d std.
- Expected turnover direction: lower

## 6. `mom_near120high`
```
rank(divide(close, ts_max(close, 120)))
```
- Rationale: Close relative to 120d high (6-month near-high anomaly, George & Hwang).
- Expected turnover direction: lower

## 7. `mom_riskadj_decay`
```
rank(ts_decay_linear(divide(returns, ts_std_dev(returns, 20)), 60))
```
- Rationale: Risk-adjusted daily returns smoothed over 60d with linear decay.
- Expected turnover direction: lower

## 8. `mom_volwt40`
```
rank(multiply(ts_mean(returns, 40), log(add(ts_mean(divide(volume, adv20), 60), 1))))
```
- Rationale: 40d momentum weighted by long-term abnormal volume - momentum on actively-traded names.
- Expected turnover direction: lower

