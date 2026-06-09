# D0 (delay=0) Alpha Mining Report — submittable factors found

Account: `huyukun662@gmail.com` (WQ user `YW92315`).
Region/universe: USA TOP3000, **delay=0**.

All numbers come from WorldQuant Brain's `/simulations` + `/alphas/{id}/check`
(the canonical backtest **and** the real submit-gate, which computes
`SELF_CORRELATION` against the account's 19 submitted alphas).
**No factor was SUBMITTED** — only simulated and `/check`-verified
("check submit"), per instruction.

## Result: 3 delay-0 factors pass ALL 8 submit gates ✅

Independently re-read via `/alphas/{id}/check` (`WQ_D0_SUBMITTABLE.json`):

| alpha_id   | SH   | FIT  | TO    | ann.ret | maxDD | self-corr | gates |
|------------|-----:|-----:|------:|--------:|------:|----------:|:-----:|
| **O097MAJR** | 2.03 | **1.70** | 0.123 | 8.8% | **3.19%** | 0.31 | **8/8 PASS** |
| LLR7mKEM   | 2.03 | 1.72 | 0.127 | — | 3.3% | 0.34 | 8/8 PASS |
| LLR7zXNM   | 2.00 | 1.68 | **0.119** | 8.9% | 3.3% | 0.33 | 8/8 PASS |
| zqWkWowV   | 2.04 | 1.69 | 0.127 | 8.7% | 3.2% | 0.30 | 8/8 PASS |

Recommended: **`O097MAJR`** — Pareto-best: a `ts_decay_linear`-smoothed
reversal diversifier simultaneously lowers turnover (0.123), lifts Fitness
(1.70), and gives the lowest drawdown (3.19%) while holding the Sharpe
margin (2.03). `LLR7zXNM` is the lowest-turnover submittable (0.119) if
turnover matters more than Sharpe headroom.

### O097MAJR — full gate table

```
LOW_SHARPE              PASS  2.03  > 2.0
LOW_FITNESS             PASS  1.70  > 1.3
LOW_TURNOVER            PASS  0.123 > 0.01
HIGH_TURNOVER           PASS  0.123 < 0.7
CONCENTRATED_WEIGHT     PASS
LOW_SUB_UNIVERSE_SHARPE PASS  > limit
SELF_CORRELATION        PASS  0.31  < 0.7
MATCHES_COMPETITION     PASS
```

### Expression

```
winsorize(
  if_else(
    is_nan(group_zscore(ts_mean(ts_backfill(vec_avg(nws12_mainz_short_interest), 22), 22), subindustry)),
    group_zscore(ts_mean(news_pct_90min, 22), subindustry),                          # book-fill (dense)
    5 * group_zscore(ts_mean(ts_backfill(vec_avg(nws12_mainz_short_interest), 22), 22), subindustry)  # short core x5
  )
  - 0.5 * group_zscore(ts_decay_linear(ts_delta(close, 5), 5), subindustry),         # SMOOTHED reversal diversifier
  std=4)
settings: USA TOP3000, delay=0, decay=10, neutralization=SUBINDUSTRY,
          truncation=0.012, pasteurization=ON
```

### Turnover / drawdown reduction (round TO-1, TO-2)

- `maxDD` is already at its floor (~3.1–3.3%, exceptional for a submittable
  alpha) and does not respond to further smoothing — it is signal-driven.
- Turnover floor at `SH >= 2.0` is **~0.119**; below that the reversal
  diversifier (which lifts SH over 2.0) loses too much of its own Sharpe
  and the alpha drops under the 2.0 gate.
- **`hump(x, h)` rejected** by this account ("exactly 1 input"), so the
  explicit-threshold turnover cap is unavailable.
- Best lever: replace the raw `ts_delta(close,5)` reversal with a
  `ts_decay_linear(ts_delta(close,5),5)`-smoothed one — lower turnover AND
  higher fitness AND lower drawdown at the same Sharpe.

### Fitness optimization (rounds FIT-1, FIT-2)

The expression is fixed; only settings/weights were swept. Fitness =
`sharpe·sqrt(|returns|/max(turnover, 0.125))`, and turnover is already at
the 0.125 floor, so gains came from Sharpe/returns, not lower turnover:

- Raising the short-core weight (×7…×12) **lowers** Sharpe (the short
  signal alone is noisier; the half-weight reversal is what lifts SH).
- `truncation` 0.015–0.012 (slightly more concentrated) is the sweet spot;
  0.01 over-concentrates and drops SH below 2.0.
- `decay` 10–12 is optimal; 14 over-smooths and drops SH.
- Adding a social-sentiment diversifier did not help (FIT stayed 1.68).
- **Structure ceiling ≈ FIT 1.69**; higher would need a structurally
  stronger / additional orthogonal signal.

### Economic rationale (3 components)

1. **Short-squeeze core** — `nws12_mainz_short_interest` (shares sold
   short, main session) 22-day-smoothed, sub-industry z-scored, weighted
   ×5. Crowded-short names carry a squeeze/short-risk premium. This is
   the high-Sharpe engine but is sparse (~86% coverage), so on its own it
   **fails** `CONCENTRATED_WEIGHT`.
2. **Book-fill** — the ~14% of names with no short-interest data are
   filled with a *dense, orthogonal* news-attention drift signal
   (`news_pct_90min`, 22d-smoothed). Every name now holds a real signal →
   `CONCENTRATED_WEIGHT` **passes** without diluting the core.
3. **Reversal diversifier** — `-0.5·group_zscore(ts_delta(close,5))`, a
   low-turnover sub-industry short-term reversal. Lifts Sharpe/Fitness and
   keeps turnover at ~0.14.

- **Regularization functions:** `winsorize` (outlier cap) + `group_zscore`
  (within-subindustry standardization).
- **Uncommon operators:** `vec_avg`, `ts_backfill`, `group_zscore`,
  `if_else`, `is_nan`.
- **IV avoided:** no `implied_volatility_*` / `option*` fields.
- **No template reuse:** freshly constructed (not Alpha101 / classical).

## How it was found (96 unique WQ-Brain simulations)

The delay-0 submit bar is far stricter than delay-1:

| IS check    | delay=1 | **delay=0** |
|-------------|--------:|------------:|
| LOW_SHARPE  |    1.25 |    **2.00** |
| LOW_FITNESS |    1.00 |    **1.30** |

PV-only reversal (rounds 1–9, 66 sims) caps at **Sharpe ~1.38** — far
short of 2.0. The breakthrough came from the prior sessions' insight
(PRs #17/#21/#22 on this repo): at delay-0 **non-IV**, Sharpe > 2.0
requires a **short-interest** core, whose sparsity must be repaired by
book-filling NaN names with a dense signal (else `CONCENTRATED_WEIGHT`
fails).

Search trail to the 3 passers (rounds SI-1…SI-5):

| round | move                                              | best outcome                 |
|-------|---------------------------------------------------|------------------------------|
| SI-1  | dense `nws12_mainz_short_interest` core + reversal | SH 2.49 / FIT 2.64, **concW FAIL** |
| SI-2  | book-fill NaN (0 / sentiment / news)              | concW PASS, SH collapses to ~1.5–1.98 |
| SI-3  | core:reversal ratio sweep                          | flat ~1.5 (fill-0 wastes book) |
| SI-4  | A1kwq1gR proportions (core ×3–6, news-drift fill) | SH 2.13 / FIT 1.08 (FIT FAIL) |
| SI-5  | cut turnover: 22d news-fill, lighter/longer reversal, higher decay | **SH 2.06 / FIT 1.63 / 8/8 PASS** |

Key lever in SI-5: turnover fell from ~0.38 to ~0.14 (slower fill + a
half-weight 5-day reversal + decay 8-12), which lifted Fitness from ~1.1
to ~1.6 while Sharpe stayed above 2.0.

## Note on "concise"

A single concentration-safe expression at delay-0 non-IV inherently needs
the `if_else` book-fill (the high-Sharpe short signal is sparse). The
factor is therefore a 3-part composite — but each part is simple and the
construction is the minimal one that satisfies `CONCENTRATED_WEIGHT`
simultaneously with `LOW_SHARPE`/`LOW_FITNESS`.

⚠️ **Check-only.** These pass the `/check` IS gates (submittable state).
The actual "Submit Alpha" click is a separate 1-concurrent quota the
account holder triggers — not done here.
