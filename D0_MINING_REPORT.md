# D0 (delay=0) Alpha Mining Report

Account: `huyukun662@gmail.com` (WQ user `YW92315`).
Region/universe: USA TOP3000. Data tier: **PV-only** (price/volume; 67
operators, no fundamental/analyst/news datasets, no STATISTICAL/FACTOR/
CROWDING neutralizations).

All numbers below come from WorldQuant Brain's `/simulations` endpoint
(the canonical backtest), **not** the local proxy. No factor was
SUBMITTED — only simulated (`check submit`), per instruction.

## 1. Headline: delay-0 has a much higher submit bar

The new account **does** support `delay=0` simulations (the prior
account `2445560398@qq.com` did not). But the delay-0 IS check limits
are far stricter than delay-1:

| IS check                | delay=1 limit | **delay=0 limit** |
|-------------------------|--------------:|------------------:|
| `LOW_SHARPE`            |          1.25 |          **2.00** |
| `LOW_FITNESS`           |          1.00 |          **1.30** |
| `HIGH_TURNOVER`         |          0.70 |              0.70 |
| `LOW_SUB_UNIVERSE_SHARPE` | (small)     |          (small)  |

To be **submittable**, all IS checks must `PASS`. At delay-0 that means
**Sharpe > 2.0 AND Fitness > 1.3** simultaneously.

## 2. What we searched (66 WQ-Brain simulations, 9 rounds)

Every expression is freshly generated (no Alpha101 / classical-template
reuse), concise, contains a **regularization function**
(`winsorize` / `group_zscore` / `rank` / `quantile` / `normalize`),
carries clear **economic meaning**, and favours **uncommon operators**
(`ts_av_diff`, `ts_zscore`, `ts_quantile`, `signed_power`, `group_zscore`,
`trade_when`, `hump`). We deliberately avoided implied-volatility (IV)
fields/operators.

Signal families covered, with the best delay-0 Sharpe each reached:

| Family (economic rationale)                                   | best D0 Sharpe |
|---------------------------------------------------------------|---------------:|
| Multi-day price reversal (overreaction)                       | ~1.0           |
| + SUBINDUSTRY neutralization (remove sector beta)             | ~1.25          |
| + decay tuning / `group_zscore` regularization                | ~1.29          |
| Intraday reversal (close-vs-open), CLV (close-in-range)       | ~1.0           |
| Overnight gap reversal                                        | ~0.4 (TO high) |
| Amihud illiquidity reversal `returns/volume`                  | ~0.05          |
| Volatility-scaled reversal (`/ ts_std_dev`)                   | ~0.7 (hurts)   |
| `ts_regression` residual reversal                             | ~0.3           |
| Overnight-momentum − intraday-reversal (Lou-Polk-Skouras)     | ~0.4–0.9       |
| **`trade_when` high-volatility-gated reversal**               | **~1.38**      |

## 3. Best delay-0 factor found (economically sound, but NOT submittable)

```
trade_when(ts_rank(abs(returns), 22) > 0.6, winsorize(-ts_delta(close, 4), std=4), -1)
settings: USA TOP3000, delay=0, decay=8, neutralization=SUBINDUSTRY,
          truncation=0.08, pasteurization=ON
WQ Brain IS:  Sharpe 1.38   Turnover 0.184   Fitness 1.18
```

Economic story: short-term price reversal (mean-reversion after
overreaction), **traded only on high-volatility days** (`ts_rank(abs(
returns),22) > 0.6` — reversal is most reliable right after a large move),
**winsorized** to cap outliers and **industry-neutralized** to strip
sector beta. It is concise, uses the uncommon `trade_when` gate, and has
the cleanest risk profile we found — but **Sharpe 1.38 < 2.0**, so it
fails the delay-0 `LOW_SHARPE` / `LOW_FITNESS` checks and is **not
submittable at delay-0**.

## 4. Conclusion

**A submittable delay-0 factor (Sharpe > 2.0) is not achievable on this
account's PV-only data tier with a concise expression.** The PV reversal
edge on USA TOP3000 caps near Sharpe ~1.4 after the strongest available
neutralization and turnover control. Reaching 2.0 at delay-0 would
require either richer datasets (fundamental / analyst / news / options —
gated behind a higher account tier) or the stronger STATISTICAL/FACTOR
neutralizations (also not available here).

## 5. The one factor that DOES pass submit (delay=1)

The same reversal core, at **delay=1** (bar 1.25 / 1.0), passes **every**
IS submit check:

```
winsorize(-ts_delta(close, 5), std=4)
settings: USA TOP3000, delay=1, decay=15, neutralization=SUBINDUSTRY,
          truncation=0.08, pasteurization=ON
WQ Brain IS:  Sharpe 1.42   Turnover 0.212   Fitness 1.19
checks: ALL PASS  (LOW_SHARPE pass, LOW_FITNESS pass, turnover pass,
        concentration pass, sub-universe pass)  ->  SUBMITTABLE
```

It is concise, regularized (`winsorize`), economically meaningful
(industry-neutral short-term reversal), and avoids IV. It is the only
candidate confirmed submittable — but it is **delay-1, not delay-0**.
