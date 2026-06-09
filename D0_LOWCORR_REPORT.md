# D0 low-correlation factor batch — fresh mechanisms vs the short-interest factors

Goal: mine a **fresh batch of D0 factors with low correlation** to the
already-mined short-interest squeeze factors (`O097MAJR`, `zqWkWowV`, …).

Correlation is measured as Pearson correlation of **daily-PnL changes**
(`scripts/pnl_corr.py`, via `/alphas/{id}/recordsets/pnl`) against the
reference short-interest factor `O097MAJR` — this is the diversification-
relevant metric (raw cumulative-PnL correlation is inflated by common drift).

## The structural frontier (D0, non-IV)

Probing every non-IV mechanism on this account established that **only
short interest reaches Sharpe > 2.0**; every orthogonal mechanism caps far
lower:

| mechanism (standalone, D0)            | best Sharpe |
|---------------------------------------|------------:|
| short interest (squeeze)              | **2.0–2.5** |
| earnings-announcement effect (ern4)   | ~1.35       |
| analyst EPS revision / earnings yield | ~0.9        |
| book/price value, ROE                 | ~0.6        |
| social sentiment, news buzz           | ~0.4        |
| pure PV reversal                      | ~1.38       |

Therefore **"submittable (SH>2.0)" and "low-correlation-with-the-short-
interest-factors" are mutually exclusive at D0 non-IV** — anything that
clears 2.0 *is* the short mechanism (correlation 0.93–0.99 to each other);
anything decorrelated is built from the weaker orthogonal mechanisms.

The fresh batch maps the whole frontier:

| alpha_id   | mechanism (no IV)                              | SH   | FIT  | dPnL-corr vs O097MAJR | submittable |
|------------|------------------------------------------------|-----:|-----:|----------------------:|:-----------:|
| O097MAJR (ref) | short-interest squeeze + news-fill + reversal | 2.03 | 1.70 | 1.00 | ✅ |
| `6XErewE7` | short(minority) + earnings-effect + value + reversal | 1.98 | 1.92 | **0.51** | ✗ (SH 1.98) |
| `mLXgVZrK` | short(×3) + heavy earnings + value             | 1.64 | 1.53 | **0.36** | ✗ |
| `Grodw623` | earnings-effect + book/price + ROE + sentiment (no short) | 1.28 | 1.07 | **0.30** | ✗ |
| `LLR9pQ6n` | earnings-effect + value (no short)             | 1.09 | 0.82 | **0.14** | ✗ |
| `O09rpmgJ` | earnings-effect + value + reversal (no short)  | 1.00 | 0.75 | **0.09** | ✗ |

## Pick by purpose

- **Near-zero correlation** (a true diversifier for the short-interest
  book): **`O09rpmgJ`** — dPnL-corr **0.09**, an earnings-effect + value +
  reversal factor with no short-interest content at all. SH 1.0 (not
  submittable on its own, but adds an almost-independent return stream).
- **Best decorrelated factor with real Sharpe**: **`Grodw623`** — corr
  0.30, SH 1.28, a clean fundamental/earnings/sentiment composite.
- **Highest Sharpe while still ~half-decorrelated**: **`6XErewE7`** —
  corr 0.51, SH 1.98, Fitness 1.92. Blends a minority short core with a
  heavy earnings+value tilt; sits just under the 2.0 submit gate.

## 6XErewE7 — the lowest-correlation *near-submittable* factor

```
winsorize(
  if_else(is_nan(SI), news_fill, 5 * SI)
  + 2.0 * group_zscore(ts_mean(ts_backfill(vec_avg(ern4_erneffct7), 22), 22), subindustry)   # earnings-announcement effect
  + 1.5 * group_zscore(ts_backfill(divide(bookvalue_ps, close), 66), subindustry)            # book/price value
  - 0.3 * group_zscore(ts_decay_linear(ts_delta(close, 5), 5), subindustry),                 # reversal
  std=4)
  with  SI = group_zscore(ts_mean(ts_backfill(vec_avg(nws12_mainz_short_interest),22),22), subindustry)
        news_fill = group_zscore(ts_mean(news_pct_90min, 22), subindustry)
settings: USA TOP3000, delay=0, decay=10, SUBINDUSTRY, truncation=0.012
SH 1.98 · FIT 1.92 · TO 0.082 · maxDD 5.1% · corr-to-short 0.51
```

Economic story: the same crowded-short squeeze engine, but with its weight
shared against two orthogonal premia — **post-earnings-announcement drift**
(`ern4_erneffct7`) and **value** (book-to-price) — plus a smoothed reversal.
The earnings + value tilt is what halves the correlation (0.93 → 0.51); it
also lifts Fitness to 1.92. The cost is ~0.05 of Sharpe, leaving it just
under the 2.0 gate.

All non-IV, regularized (`winsorize`/`group_zscore`), uncommon operators
(`vec_avg`, `ts_backfill`, `ts_decay_linear`, `if_else`), no template reuse.

## Takeaway

If the priority is a **decorrelated** new factor, `Grodw623` / `O09rpmgJ`
deliver corr 0.09–0.30 (genuinely independent return streams) at SH ~1.0–1.3.
If the priority stays **submittable**, the only option remains a short-
interest factor (`O097MAJR`, corr ~1.0 to the family). `6XErewE7` is the
best compromise on the frontier (corr 0.51, SH 1.98) but is not quite
submittable. Reaching SH>2.0 *and* corr<0.7 simultaneously is not
attainable on this account's non-IV data tier.
