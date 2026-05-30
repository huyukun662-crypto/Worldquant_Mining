# Second D0 factor — uncorrelated with the short-interest winner

## Goal
Mine a second delay-0 factor **uncorrelated** with the short-interest
winner `KPkVxEb1` (the regularized SH-2.08 alpha), to act as a genuine
diversifier.

## Approach
Hunt economically-orthogonal signal families (value, quality, analyst
estimates, earnings surprise, news) rather than anything short/positioning
related. Short interest captures *short-side crowding*; an uncorrelated
factor must be driven by something else.

## Orthogonal-core scan (D0, TOP3000, INDUSTRY, batches o1–o5)
| core | family | SH | note |
|---|---|---:|---|
| analyst forecast **dispersion** `(high-low)/mean` | analyst4 | **1.01** | best orthogonal core |
| analyst predicted-uncertainty `pu` | analyst4 | 0.86 | very low turnover |
| dispersion + value | mixed | 0.92 | |
| book-to-price | fundamental6 | 0.69 | classic value, slow |
| analyst revision (consensus Δ) | analyst4 | 0.51 | |
| ROE | fundamental6 | 0.33 | |
| earnings surprise (eps ratio / growth) | news12/fnd | ≤0.05 | weak/negative at D0 |
| earnings yield (ebit/EV) | fundamental6 | 0.17 | |

**Orthogonal D0 signals cap at SH ≈ 1.0.** Short interest remains the only
D0 family reaching SH ≈ 2.0 — so an *uncorrelated* factor cannot also clear
the 2.0 submit gate at delay 0. The deliverable here is a genuine
diversifier (SH ≈ 1.0), not an independently-submittable alpha.

## Orthogonality CONFIRMED (the key result)
Daily-PnL Pearson correlation, measured over 1,235 days via
`scripts/d0_corr.py`:

```
KPkVxEb1 (short-interest, SH 2.08)  vs  kqQvJ9ad (analyst dispersion, SH 1.01)
    corr = -0.010
```

**Essentially zero correlation** — the analyst-forecast-dispersion factor
is a true orthogonal diversifier to the short-interest winner, exactly as
the economic intuition predicts (short crowding and analyst disagreement
are independent return drivers).

## Construction notes / pitfalls
- Analyst fields update sparsely → **must `ts_backfill`** before any
  time-series op, else turnover explodes (raw dispersion TO=1.57 vs
  backfilled TO=0.25).
- The `anl4_dez1*v4_est/_preest` "detailed-estimate revision" fields (cov
  1.0) are **event-typed**: `ts_backfill`/`subtract`/`ts_mean` all reject
  them, so dense revision momentum is not simply constructible.
- Cross-field EPS surprise hits **unit mismatches** (`news_eps_actual`
  Unit[] vs `est_epsr` Unit[CSShare:-1]); only same-unit arithmetic works.
