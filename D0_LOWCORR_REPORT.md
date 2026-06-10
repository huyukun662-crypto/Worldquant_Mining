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

---

## Update: a FRESH *submittable* decorrelated factor — `d5QOMdxx`

By keeping a heavy short core but adding only a **light orthogonal tilt**
(the QPEzl0Er insight: ~15-20% non-short content drops correlation from
0.93 to ~0.5 while short keeps SH>2.0), we get a submittable factor that
is genuinely decorrelated from this session's `O097MAJR`:

```
d5QOMdxx  (USA TOP3000, delay=0, decay=4, INDUSTRY, truncation=0.02)
  0.8 * book-filled short-interest core
+ 0.2 * group_zscore(analyst-dispersion + 0.5*forecast-uncertainty
                      + 0.4*book/price + 0.3*ROE + 0.4*earnings-effect)
  all winsorized, INDUSTRY-neutral
SH 2.05 · FIT 2.09 · TO 0.135 · ann.ret 14.1% · maxDD 7.3% · 8/8 PASS
dPnL-corr vs O097MAJR = 0.54   (vs QPEzl0Er = 0.86)
```

It adds the fresh `ern4_erneffct7` earnings-announcement ingredient to a
0.8/0.2 short/fundamental split (distinct from QPEzl0Er's 0.85/0.15
analyst-only), and is **submittable AND 0.54-correlated** to O097MAJR.

### The submittable space is ~1-dimensional

Measuring the existing SH>2.0 factors confirms the structure: the only
submittable mechanism is short-interest, and the decorrelating *tilts*
that preserve SH>2.0 fall into two families —
- **reversal tilt** → the `O097MAJR` family
- **analyst-dispersion tilt** → the `QPEzl0Er` / `d5QOMdxx` family

A new submittable factor decorrelates from one family (`d5QOMdxx` is 0.54
to O097MAJR) but stays correlated (~0.86) to its own family. Decorrelating
from **both** simultaneously requires dropping short weight enough that
SH falls under 2.0 (the `Grodw623`/`O09rpmgJ` orthogonal factors, corr
0.09-0.30, SH 1.0-1.3).

### Bottom line for "fresh + low-correlation"
- vs this session's factor (`O097MAJR`): **`d5QOMdxx`** is fresh,
  submittable, and decorrelated (0.54).
- vs the whole pool / a true independent stream: **`O09rpmgJ`** (corr
  0.09) or **`Grodw623`** (corr 0.30), at the cost of submittability.

---

## Final: `QPQK17p5` — best-overall submittable D0 factor (3rd family)

A **vol-return-covariance diversifier** (neither the reversal nor the
analyst tilt) on the short core gives the best factor of the whole search:

```
winsorize(
  if_else(is_nan(SI), news_fill, 5 * SI)                                   # short-squeeze core, book-filled
  - 0.5 * group_zscore(ts_covariance(returns, volume, 20), subindustry),   # vol-return covariance diversifier
  std=4)
  SI = group_zscore(ts_mean(ts_backfill(vec_avg(nws12_mainz_short_interest),22),22), subindustry)
  news_fill = group_zscore(ts_mean(news_pct_90min, 22), subindustry)
settings: USA TOP3000, delay=0, decay=10, SUBINDUSTRY, truncation=0.012
SH 2.23 · FIT 1.86 · TO 0.107 · ann.ret 8.7% · maxDD 3.35% · 8/8 PASS
official SELF_CORRELATION vs submitted pool = 0.296  (limit 0.7)
```

- Highest Sharpe of all submittable factors found (2.23 vs 2.03-2.06).
- Concise: short core + ONE diversifier, same complexity as O097MAJR.
- Regularized (`winsorize`, `group_zscore`); uncommon ops `ts_covariance`,
  `vec_avg`, `ts_backfill`, `if_else`; no IV.
- The `ts_covariance(returns, volume, 20)` leg (volume-amplified momentum
  reversal: names where returns co-move with volume get faded) is its own
  weak-but-orthogonal mechanism — standalone SH only 0.2-0.5, yet as a
  diversifier it beats both the reversal (2.03) and analyst (2.05) tilts.

### Correlation caveats (measured)
- Official submit-gate self-correlation (vs the 19 SUBMITTED alphas): **0.30** ✅
- dPnL corr vs the *unsubmitted* O097MAJR: 0.81 (same short core) — if you
  submit several of this short family, the FIRST one enters the pool and
  the others' SELF_CORRELATION will then jump; submit only one of the
  short-core factors (QPQK17p5 is the best), then pick later factors from
  other mechanisms.

### Dead ends established this round (so they're not re-walked)
- `ern4_*` earnings-effect fields are IV-derived: every factor containing
  them correlates 0.73-0.81 with the submitted IV alpha `j21EEbx9` → fails
  SELF_CORRELATION. Avoid ern4 when low correlation is required.
- All slow fundamental tilts (value/ROE/sentiment composites) also land
  ~0.78 on `j21EEbx9` (low-turnover books overlap).
- Standalone D0 Sharpe of unique mechanisms: covariance 0.5, turnover
  anomaly -0.3, buzz momentum 0.39, low-vol anomaly 0.18 (dead), Ravenpack
  ssc ~0.1 (dead), dividend yield (turnover explodes).
